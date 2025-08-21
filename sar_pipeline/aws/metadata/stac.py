import json
from pathlib import Path
from typing import Literal
import rasterio
import pyproj
import pystac
from shapely.geometry import shape, box, mapping
from dateutil.parser import isoparse
import requests
import datetime
import re
import numpy as np
import os

import dem_handler
import sar_pipeline
from sar_pipeline.aws.metadata.h5 import H5Manager
from sar_pipeline.aws.metadata.odc import (
    get_odc_product_name,
    make_rtc_s1_static_s3_subpath,
)
from sar_pipeline.aws.preparation.burst_utils import (
    make_rtc_s1_s3_subpath,
    make_rtc_s1_static_s3_subpath,
)
from sar_pipeline.utils.spatial import (
    polygon_str_to_geojson,
    reproject_bbox_to_geometry,
)
from sar_pipeline.utils.aws import find_s3_filepaths_from_suffixes
from sar_pipeline.aws.metadata.filetypes import (
    RENAME_ASSET_FILETYPES,
    REQUIRED_ASSET_FILETYPES,
    ASSET_FILETYPE_TO_DESCRIPTION,
    ASSET_FILETYPE_TO_MEDIATYPE,
    ASSET_FILETYPE_TO_ROLES,
    ASSET_FILETYPE_TO_TITLE,
)

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class BurstH5toStacManager:
    """utility class to convert burst .h5 metadata to a STAC item data"""

    def __init__(
        self,
        h5_filepath: Path,
        product: Literal["RTC_S1", "RTC_S1_STATIC"],
        product_id: str,
        backscatter_convention: Literal["gamma0", "sigma0", "beta0"],
        collection_number: int,
        s3_bucket: str,
        s3_project_folder: str,
        s3_region: str = "ap-southeast-2",
    ):
        """
        Parameters
        ----------
        h5_filepath : Path
            Local path to the .h5 file output from the opera/RTC process
        product: ["RTC_S1","RTC_S1_STATIC"]
            The product being made. RTC_S1 or RTC_S1_STATIC
        product_id: str:
            The product id for the burst run. This is common across files.
            e.g. ga_s1_nrb-static_v0.1.0_T070-149815-IW3_20140403
        backscatter_convention: ["gamma0","sigma0","beta0"]
            normalisation convention of the backscatter product
        collection_number: int
            The collection number associated with the product
        s3_bucket : str
            The S3 bucket where data will be uploaded
        s3_project_folder : str
            The project folder in the S3 bucket if required. Note that
            the odc_product_name will be appended to this folder path.
        s3_region : str, optional
            The region of the S3 bucket, by default "ap-southeast-2"
        """
        self.h5_filepath = h5_filepath
        self.h5 = H5Manager(self.h5_filepath)  # class to help get values from .h5 file
        self.id = product_id
        self.burst_folder = h5_filepath.parent
        self.product = self._check_valid_product(product)
        self.backscatter_convention = backscatter_convention
        self.burst_id = self.h5.search_value("burstID")
        self.polarisations = self.h5.search_value("listOfPolarizations")
        self.collection_number = collection_number
        self.odc_product_name = get_odc_product_name(
            self.product, self.collection_number, self.polarisations
        )
        self.stac_extensions = [
            "https://stac-extensions.github.io/product/v0.1.0/schema.json",
            "https://stac-extensions.github.io/sar/v1.1.0/schema.json",
            "https://stac-extensions.github.io/projection/v2.0.0/schema.json",
            "https://stac-extensions.github.io/sat/v1.1.0/schema.json",
            "https://stac-extensions.github.io/sentinel-1/v0.2.0/schema.json",
            "https://stac-extensions.github.io/processing/v1.2.0/schema.json",
            "https://stac-extensions.github.io/storage/v2.0.0/schema.json",
        ]
        if self.product == "RTC_S1":
            self.stac_extensions += [
                "https://stac-extensions.github.io/ceos-ard/v0.2.0/schema.json"
            ]
        self.s3_bucket = s3_bucket
        self.s3_project_folder = s3_project_folder
        self.s3_region = s3_region
        self.start_dt = isoparse(
            self.h5.search_value("identification/zeroDopplerStartTime")
        )
        self.end_dt = isoparse(
            self.h5.search_value("identification/zeroDopplerEndTime")
        )
        self.processed_dt = isoparse(
            self.h5.search_value("identification/processingDateTime")
        )
        self.projection_epsg = self.h5.search_value(
            "data/projection"
        )  # code, e.g. 4326, 3031
        if self.product == "RTC_S1":
            # NOTE - boundingPolygon does not correctly encompass the burst data
            # We therefore use the boundingBox in native coords converted to 4326
            # below can be uncommented to return to the boundingPolygon
            # self.geometry_4326 = polygon_str_to_geojson(
            #     self.h5.search_value("boundingPolygon")
            # )

            polygon_4326 = reproject_bbox_to_geometry(
                self.h5.search_value("boundingBox"),
                src_crs=self.projection_epsg,
                trg_crs=4326,
                n_segments=5,
            )
            self.geometry_4326 = mapping(polygon_4326)
            self.bbox_4326 = polygon_4326.bounds

        elif self.product == "RTC_S1_STATIC":
            # boundingPolygon is not included, set this to be bbox
            polygon_4326 = reproject_bbox_to_geometry(
                self.h5.search_value("boundingBox"),
                src_crs=self.projection_epsg,
                trg_crs=4326,
                n_segments=5,
            )
            self.geometry_4326 = mapping(polygon_4326)
            self.bbox_4326 = polygon_4326.bounds

        self.burst_s3_subfolder = self._make_s3_subfolder()
        self.bucket_href = f"https://{self.s3_bucket}.s3.{self.s3_region}.amazonaws.com"
        self.base_href = f"{self.bucket_href}/{self.burst_s3_subfolder}"
        # browse link the view all product files in folder
        self.browse_href = (
            f"{self.bucket_href}/index.html?prefix={self.burst_s3_subfolder}"
        )

    def _check_valid_product(self, product):
        "check the product is valid"
        if product not in ["RTC_S1", "RTC_S1_STATIC"]:
            raise ValueError("Invalid product")
        return product

    def _make_s3_subfolder(self):
        "make the s3 subfolder destination based on the product"
        if self.product == "RTC_S1":
            # include acquisition dates for S1_RTC
            return make_rtc_s1_s3_subpath(
                s3_project_folder=self.s3_project_folder,
                collection_number=self.collection_number,
                burst_polarisations=self.polarisations,
                burst_id=self.burst_id,
                year=self.start_dt.year,
                month=self.start_dt.month,
                day=self.start_dt.day,
            )

        elif self.product == "RTC_S1_STATIC":
            # static products are date independent
            return make_rtc_s1_static_s3_subpath(
                s3_project_folder=self.s3_project_folder,
                collection_number=self.collection_number,
                burst_id=self.burst_id,
            )

    def _extract_doi_link(self, text: str) -> str:
        """extracts the doi reference from a given string and converts
        it to a url"""
        doi_match = re.search(r"10\.\d{4,9}/[\w.-]*\w", text)
        return f"https://doi.org/{doi_match.group()}" if doi_match else None

    def _extract_http_link(self, text: str) -> str:
        """Extracts the first HTTP or HTTPS link from a given string"""
        url_match = re.search(r"https?://\S+", text)
        return url_match.group() if url_match else None

    def _get_product_timeliness_category(
        self, acquisition_dt: datetime.datetime, processed_dt: datetime.datetime
    ) -> Literal["NRT", "STC", "NTC"]:
        """get the timeliness based on the acquisition and processed times
        rules defined in - https://github.com/stac-extensions/product

        Returns
        -------
        str
            NRT = Near Real Time
            STC = Short Time Critical
            NTC = Non Time-Critical
        """
        delta_hrs = (processed_dt - acquisition_dt).total_seconds() / 3600
        if delta_hrs < 3:
            return "NRT"
        elif delta_hrs < 36:
            return "STC"
        else:
            return "NTC"

    def make_stac_item_from_h5(self):
        """Make a pystac.item.Item for the given burst using key properties
        taken from the .h5 file.
        """

        # Some base properties need to be defined
        base_properties = {
            "gsd": self.h5.search_value("xCoordinateSpacing"),
            "constellation": "Sentinel-1",
            "platform": self.h5.search_value("platform"),
            "instruments": [self.h5.search_value("instrumentName")],
            "created": self.h5.search_value("identification/processingDateTime"),
        }

        self.item = pystac.Item(
            id=self.id,
            geometry=self.geometry_4326,
            bbox=self.bbox_4326,
            datetime=self.start_dt,
            start_datetime=self.start_dt,
            end_datetime=self.end_dt,
            collection=self.odc_product_name,
            properties=base_properties,
            stac_extensions=self.stac_extensions,
        )

    def add_properties_from_h5(self):
        """Map required properties from the .h5 file"""

        # add odc specific fields
        self.item.properties["odc:product"] = (
            self.odc_product_name
        )  # this needs to  dynamic based on the pol files and match odc product
        self.item.properties["odc:product_family"] = "sar_ard"
        self.item.properties["odc:region_code"] = self.burst_id
        self.item.properties["odc:producer"] = "ga.gov.au"
        self.item.properties["odc:dataset_version"] = self.h5.search_value(
            "identification/productVersion"
        )

        # add product stac extension properties
        self.item.properties["product:type"] = self.product
        # remove timeliness as not required. May re-add if approach is determined.
        # self.item.properties["product:timeliness"] = "TODO"
        # self.item.properties["product:timeliness_category"] = (
        #     self._get_product_timeliness_category(self.start_dt, self.processed_dt)
        # )

        # add ceos-ard stac extension properties
        if self.product == "RTC_S1":
            self.item.properties["ceosard:type"] = "radar"
            self.item.properties["ceosard:specification"] = "NRB"
            self.item.properties["ceosard:specification_version"] = "5.5"

        # add projection (proj) stac extension properties
        self.item.properties["proj:code"] = f"EPSG:{self.projection_epsg}"
        self.item.properties["proj:bbox"] = self.h5.search_value("boundingBox")
        self.item.properties["proj:wkt2"] = pyproj.CRS.from_epsg(
            self.projection_epsg
        ).to_wkt()

        # add the sar stac extension properties
        self.item.properties["sar:frequency_band"] = self.h5.search_value("radarBand")
        if self.product == "RTC_S1":
            self.item.properties["sar:center_frequency"] = (
                float(self.h5.search_value("centerFrequency")) / 1e9
            )  # GHz
            self.item.properties["sarard:center_frequency_unit"] = "GHz"
            self.item.properties["sar:polarizations"] = self.polarisations
        else:
            # add all to static layer
            self.item.properties["sar:polarizations"] = ["HH", "VV", "HV", "VH"]
        self.item.properties["sar:observation_direction"] = self.h5.search_value(
            "lookDirection"
        )
        self.item.properties["sar:beam_ids"] = [self.h5.search_value("subSwathID")]
        self.item.properties["sar:instrument_mode"] = self.h5.search_value(
            "acquisitionMode"
        )

        # add sat stac extension properties
        self.item.properties["sat:orbit_state"] = self.h5.search_value(
            "orbitPassDirection"
        )
        self.item.properties["sat:absolute_orbit"] = self.h5.search_value(
            "absoluteOrbitNumber"
        )
        self.item.properties["sat:relative_orbit"] = self.h5.search_value("trackNumber")
        self.item.properties["sat:orbit_cycle"] = 12

        # add sentinel-1 stac extension properties - https://github.com/stac-extensions/sentinel-1
        self.item.properties["s1:orbit_source"] = self.h5.search_value("orbitType")

        # add processing stac extension specification
        self.item.properties["processing:level"] = self.h5.search_value(
            "identification/productLevel"
        )
        self.item.properties["processing:facility"] = "Geoscience Australia"
        self.item.properties["processing:datetime"] = self.h5.search_value(
            "identification/processingDateTime"
        )
        self.item.properties["processing:version"] = str(
            self.h5.search_value("identification/productVersion")
        )
        self.item.properties["processing:software"] = {
            "isce3": self.h5.search_value("algorithms/isce3Version"),
            "s1Reader": self.h5.search_value("algorithms/s1ReaderVersion"),
            "GeoscienceAustralia/RTC": self.h5.search_value(
                "algorithms/softwareVersion"
            ),
            "sar-pipeline": sar_pipeline.__version__,
            "dem-handler": dem_handler.__version__,
        }

        # proposed sarard stac extension properties
        self.item.properties["sarard:source_id"] = self.h5.search_value("l1SlcGranules")
        self.item.properties["sarard:source_geometry"] = "slant range"
        self.item.properties["sarard:scene_id"] = self.h5.search_value("l1SlcGranules")[
            0
        ].replace(".SAFE", "")
        self.item.properties["sarard:burst_id"] = self.burst_id
        self.item.properties["sarard:beam_id"] = self.h5.search_value("subSwathID")
        self.item.properties["sarard:orbit_files"] = self.h5.search_value(
            "orbitFiles"
        )  # Link to a file containing the orbit state vectors.
        self.item.properties["sarard:UL_longitude"] = self.bbox_4326[0]  # min_lon
        self.item.properties["sarard:UL_latitude"] = self.bbox_4326[3]  # max_lat
        self.item.properties["sarard:LR_longitude"] = self.bbox_4326[2]  # max_lon
        self.item.properties["sarard:LR_latitude"] = self.bbox_4326[1]  # min_lat
        self.item.properties["sarard:pixel_spacing_x"] = abs(
            self.h5.search_value("xCoordinateSpacing")
        )
        self.item.properties["sarard:pixel_spacing_y"] = abs(
            self.h5.search_value("yCoordinateSpacing")
        )
        self.item.properties["sarard:pixel_spacing_unit"] = "metre"
        self.item.properties["sarard:resolution_x"] = abs(
            self.h5.search_value("xCoordinateSpacing")
        )
        self.item.properties["sarard:resolution_y"] = abs(
            self.h5.search_value("yCoordinateSpacing")
        )
        self.item.properties["sarard:resolution_unit"] = "metre"
        self.item.properties["sarard:speckle_filter_applied"] = self.h5.search_value(
            "filteringApplied"
        )
        self.item.properties["sarard:speckle_filter_type"] = ""
        self.item.properties["sarard:speckle_filter_window"] = ()
        # convert to preferred format, gamma0 -> Gamma-0
        self.item.properties["sarard:measurement_type"] = {
            "gamma0": "Gamma-0",
            "sigma0": "Sigma-0",
            "beta0": "Beta-0",
        }[self.backscatter_convention]
        self.item.properties["sarard:measurement_convention"] = self.h5.search_value(
            "outputBackscatterExpressionConvention"
        )
        self.item.properties["sarard:conversion_eq"] = self.h5.search_value(
            "outputBackscatterDecibelConversionEquation"
        )
        if self.product == "RTC_S1":
            self.item.properties["sarard:noise_removal_applied"] = self.h5.search_value(
                "noiseCorrectionApplied"
            )

        # additional non required parameters for atmosphere that would be good to have
        self.item.properties["sarard:static_tropospheric_correction_applied"] = (
            self.h5.search_value("staticTroposphericGeolocationCorrectionApplied")
        )
        self.item.properties["sarard:wet_tropospheric_correction_applied"] = (
            self.h5.search_value("wetTroposphericGeolocationCorrectionApplied")
        )
        self.item.properties["sarard:bistatic_correction_applied"] = (
            self.h5.search_value("bistaticDelayCorrectionApplied")
        )
        self.item.properties["sarard:ionospheric_correction_applied"] = False

        # TODO when official document, link the study supporting these values
        self.item.properties["sarard:geometric_accuracy_ALE"] = 2.94
        self.item.properties["sarard:geometric_accuracy_rmse"] = 3.08
        self.item.properties["sarard:geometric_accuracy_range"] = 1.63
        self.item.properties["sarard:geometric_accuracy_azimuth"] = 1.92
        self.item.properties["sarard:geometric_accuracy_unit"] = "metre"

        # add the storage stac extension properties
        self.item.properties["storage:schemes"] = {
            "aws-std": {
                "type": "aws-s3",
                "platform": "https://{bucket}.s3.{region}.amazonaws.com",
                "bucket": f"{self.s3_bucket}",
                "region": f"{self.s3_region}",
                "requester_pays": True,
            }
        }

    def add_fixed_links(self):
        """add fixed links that are not expected to change frequently"""

        # add the link the the EGM_08 GEOID
        self.item.add_link(
            pystac.Link(
                rel="geoid-source",
                target="https://aria-geoid.s3.us-west-2.amazonaws.com/us_nga_egm2008_1_4326__agisoft.tif",
                media_type=pystac.media_type.MediaType.GEOTIFF,
            )
        )

    def add_dynamic_links_from_h5(self):
        """add links to the stac item from the .h5 file"""

        # link to the ceos-ard product family specification
        self.item.add_link(
            pystac.Link(
                rel="ceos-ard-specification",
                target=self.h5.search_value(
                    "identification/ceosAnalysisReadyDataDocumentIdentifier"
                ),
                media_type=pystac.media_type.MediaType.PDF,
            )
        )

        # link to the source SLC
        self.item.add_link(
            pystac.Link(
                rel="derived-from",
                target=self.h5.search_value("sourceData/dataAccess"),
            )
        )

        # Add link to the DEM - extract link from description
        self.item.add_link(
            pystac.Link(
                rel="dem-source",
                target=self._extract_http_link(self.h5.search_value("demSource")),
                media_type=pystac.media_type.MediaType.HTML,
            )
        )

        # Add link to the RTC algorithm, get it from the reference
        if self.backscatter_convention != "beta0":
            ref_text = self.h5.search_value(
                "radiometricTerrainCorrectionAlgorithmReference"
            )
            self.item.add_link(
                pystac.Link(
                    rel="rtc-algorithm",
                    target=self._extract_doi_link(ref_text),
                    media_type=pystac.media_type.MediaType.HTML,
                )
            )

        # Add link to the geocoding algorithm, get it from the reference
        ref_text = self.h5.search_value("geocodingAlgorithmReference")
        self.item.add_link(
            pystac.Link(
                rel="geocoding-algorithm",
                target=self._extract_doi_link(ref_text),
                media_type=pystac.media_type.MediaType.HTML,
            )
        )

        # Add link to the noise removal, get it from the reference
        if self.product == "RTC_S1":
            ref_text = self.h5.search_value("noiseCorrectionAlgorithmReference")
            self.item.add_link(
                pystac.Link(
                    rel="noise-correction",
                    target=self._extract_http_link(ref_text),
                    media_type=pystac.media_type.MediaType.PDF,
                )
            )

    def add_metadata_links(
        self,
        stac_filepath: Path | str,
        h5_filepath: Path | str,
        runconfig_filepath: Path | str,
    ):
        """Add:
            - Link to self / STAC metadata doc,
            - Link to the h5 metadata file
            - Link to the processing config yaml file
            - Link to the product folder in s3 that can be used for browsing

        This will be appended to the base_href for product.

        Parameters
        ----------
        stac_filepath : Path | str
            Filepath of the stac file
        h5_filepath: Path | str
            Filepath of the .h5 file
        runconfig_filepath: Path | str
            Filepath of the config .yaml
        """

        if not Path(h5_filepath).exists():
            raise FileNotFoundError(
                f"Error setting metadata stac links. The required metadata file does not exist : {h5_filepath}"
            )
        self.item.add_link(
            pystac.Link(
                rel="h5-metadata",
                target=f"{self.base_href}/{Path(h5_filepath).name}",
                media_type=pystac.media_type.MediaType.HDF5,
            )
        )

        if not Path(runconfig_filepath).exists():
            raise FileNotFoundError(
                f"Error setting metadata stac links. The required metadata file does not exist : {runconfig_filepath}"
            )
        self.item.add_link(
            pystac.Link(
                rel="processing-config",
                target=f"{self.base_href}/{Path(runconfig_filepath).name}",
                media_type="application/yaml",
            )
        )

        # link to product folder for browsing
        self.item.add_link(
            pystac.Link(
                rel="browse",
                target=f"{self.browse_href}",
                media_type=pystac.media_type.MediaType.HTML,
            )
        )

        # the stac file gets referenced as self. We do not check if it
        # exists yet as it is saved after this process once all info as been added.
        self.item.add_link(
            pystac.Link(
                rel="self",
                target=f"{self.base_href}/{Path(stac_filepath).name}",
                media_type=pystac.media_type.STAC_JSON,
            )
        )

    def add_collection_link(
        self,
        prod_stac_href: str = "https://explorer.dea.ga.gov.au/stac/collections",
        dev_stac_href: str = "https://explorer.dev.dea.ga.gov.au/stac/collections",
        PRODUCTION: bool = True,
    ):
        """Add the link the the stac collection. The link is different pending
        if the product is to be indexed into the dev or prod ODC. This is handled
        as a downstream process and must be communicated to ensure this collection
        link is correct.

        Parameters
        ----------
        prod_stac_href : str, optional
            Link to production collection, by default "https://explorer.dea.ga.gov.au/stac/collections"
        dev_stac_href : str, optional
            link to to development collection, by default "https://explorer.dev.dea.ga.gov.au/stac/collections"
        PRODUCTION : bool, optional
            Whether to use the production collection, by default True. Set False for testing in dev odc.
        """

        if PRODUCTION:
            stac_href = f"{prod_stac_href}/{self.odc_product_name}"
            logger.info(
                f"STAC collection references the production environment: {stac_href}"
            )
        else:
            stac_href = f"{dev_stac_href}/{self.odc_product_name}"
            logger.warning(
                f"STAC collection references the development environment: {stac_href}"
            )

        self.item.add_link(
            pystac.Link(
                rel="collection",
                target=stac_href,
                media_type=pystac.media_type.STAC_JSON,
            )
        )

    def rename_asset_files(self, burst_folder: Path):
        """Rename the assets in the burst folder. Backscatter files will include the normalization
        convention type in the filename. e.g. HH.tif -> HH_gamma0.tif and other filetypes will be
        changed from '_' separated to '-' separated for consistency. e.g. incidence_angle.tif ->
        incidence-angle.tif.

        Parameters
        ----------
        burst_folder : Path
            path to the local folder containing output products for a single burst.
            e.g. /path/to/my/scene_burst/t070_149813_iw2
        """

        # get the list of files
        burst_files = [x for x in burst_folder.iterdir()]

        for f in burst_files:
            for old_suffix in RENAME_ASSET_FILETYPES.keys():
                new_suffix = RENAME_ASSET_FILETYPES[old_suffix]
                new_suffix = new_suffix.replace(
                    "BACKSCATTER-CONVENTION", self.backscatter_convention
                )
                if str(f.name) == f"{self.id}{old_suffix}":
                    # backscatter convention will be added here
                    new_path = f.with_name(f.name.replace(old_suffix, new_suffix))
                    f.rename(new_path)
                    break  # once renamed, move to next file

    def add_assets_from_folder(
        self, burst_folder: Path, add_shape_transform_to_properties: bool = True
    ):
        """Add the asset files from the local burst folder

        Parameters
        ----------
        burst_folder : Path
            path to the local folder containing output products for a single burst.
            e.g. /path/to/my/scene_burst/t070_149813_iw2
        add_shape_transform_to_properties: bool
            If true, shape and transform will be to the stac properties.
            This is the top level of the document so therefore assumes these
            values consistent across all tifs for the given burst. i.e. all
            tifs have the same shape.

        Raises
        ------
        FileNotFoundError
            If a required asset is missing
        ValueError
            If more than 1 file is found for a required asset.
        """

        # list the files in the burst folder
        burst_files = [x for x in burst_folder.iterdir()]

        # remove polarizations we don't have from the required products
        # e.g. don't try add HH if it did not exist in original source data
        if self.product == "RTC_S1":
            pols = self.polarisations
            ignore_assets = [
                f"_{p}-{self.backscatter_convention}.tif"
                for p in ["HH", "HV", "VV", "VH"]
                if p not in pols
            ]
            included_pol_assets = [
                f"_{p}-{self.backscatter_convention}.tif" for p in pols
            ]
            required_asset_filetypes = REQUIRED_ASSET_FILETYPES[self.product][
                self.backscatter_convention
            ]
        elif self.product == "RTC_S1_STATIC":
            # no pol for static products, only auxiliary files
            pols = []
            included_pol_assets = []
            ignore_assets = []  # pols already excluded from REQUIRED_ASSET_FILETYPES
            required_asset_filetypes = REQUIRED_ASSET_FILETYPES[self.product]

        included_asset_filetypes = [
            x for x in required_asset_filetypes if x not in ignore_assets
        ]

        # iterate through the included/required assets and add to the STAC item
        for asset_filetype in included_asset_filetypes:
            # map the asset_filetype to important parameters
            asset_title = ASSET_FILETYPE_TO_TITLE[asset_filetype]
            asset_description = ASSET_FILETYPE_TO_DESCRIPTION[asset_filetype]
            asset_roles = ASSET_FILETYPE_TO_ROLES[asset_filetype]
            asset_mediatype = ASSET_FILETYPE_TO_MEDIATYPE[asset_filetype]
            asset_filepaths = [
                x for x in burst_files if x.name == f"{self.id}{asset_filetype}"
            ]
            logger.info(f"{self.id}{asset_filetype}")
            if len(asset_filepaths) == 0:
                raise FileNotFoundError(
                    f'The required asset: "{asset_title}" is missing from burst folder: "{burst_folder}"'
                )
            if len(asset_filepaths) > 1:
                raise ValueError(
                    f'Expected 1 file for asset: "{asset_title}", {len(asset_filepaths)} found in burst folder: "{burst_folder}"'
                )
            asset_filepath = asset_filepaths[0]

            # define raster parameters
            if asset_filetype.endswith(".tif"):
                with rasterio.open(asset_filepath) as r:
                    raster_sampling = r.tags().get("AREA_OR_POINT", "").lower()
                    shape = r.shape
                    transform = list(r.transform)
                    extra_fields = {
                        "proj:shape": shape,
                        "proj:transform": transform,
                        "proj:code": str(r.crs),
                        "raster:data_type": r.dtypes[0],
                        "raster:sampling": raster_sampling,
                        "raster:nodata": (
                            r.nodata
                            if (
                                isinstance(r.nodata, (float, int))
                                and not np.isnan(r.nodata)
                            )
                            else str(r.nodata)
                        ),
                    }
                    # add pixel coordinate convention
                    if "area" in raster_sampling:
                        extra_fields["raster:pixel_coordinate_convention"] = "pixel ULC"
                    elif "point" in raster_sampling:
                        extra_fields["raster:pixel_coordinate_convention"] = (
                            "pixel centre"
                        )

                    if asset_filetype == "_mask.tif":
                        extra_fields["raster:values"] = {
                            "shadow": 1,
                            "layover": 2,
                            "shadow_and_layover": 3,
                            "invalid_sample": 255,
                        }
                    if asset_filetype in included_pol_assets:
                        # need to add a processing property to satisfy the
                        # processing stac requirements
                        extra_fields["processing:level"] = self.item.properties[
                            "processing:level"
                        ]

                    if add_shape_transform_to_properties:
                        self.item.properties["proj:shape"] = shape
                        self.item.properties["proj:transform"] = transform
                        # add ones required for ceos ard
                        self.item.properties["sarard:number_of_lines"] = shape[0]
                        self.item.properties["sarard:number_of_pixels_per_line"] = (
                            shape[1]
                        )

            else:
                extra_fields = {}

            # add the asset to the STAC item
            self.item.add_asset(
                asset_title,
                pystac.asset.Asset(
                    href=f"{self.base_href}/{asset_filepath.name}",
                    title=asset_title,
                    description=asset_description,
                    roles=asset_roles,
                    media_type=asset_mediatype,
                    extra_fields=extra_fields,
                ),
            )

    def add_linked_static_layers_as_assets_to_stac(
        self, stac_suffix_string: str = "stac-item.json"
    ):
        """add the static layer assets to the STAC metadata file. This is
        achieved by reading in the STAC metadata file associated with the
        static layers themselves

        Parameters
        ----------
            stac_suffix_string : The 'endswith' file string to search for in the
            static layers s3 bucket to find the stac item metadata file.
            e.g. stac-item.json -> the following file will be found
                ga_s1_nrb-static_v0.1.0_T070-149815-IW3_20140403.stac-item.json

        """

        # get the path to the static layer folder in AWS S3
        burst_static_layer_s3_subpath = make_rtc_s1_static_s3_subpath(
            self.s3_project_folder, self.collection_number, self.burst_id
        )

        logger.info(
            f"Searching for '{stac_suffix_string}' in AWS S3 burst static layer folder: {burst_static_layer_s3_subpath}"
        )

        # search for the stac-item in the burst folder
        s3_static_layer_files = find_s3_filepaths_from_suffixes(
            self.s3_bucket,
            burst_static_layer_s3_subpath,
            suffixes=[stac_suffix_string],
        )

        # get the keys containing the proposed suffix
        s3_static_layer_files = s3_static_layer_files[stac_suffix_string]

        if len(s3_static_layer_files) != 1:
            raise ValueError(
                f"Expecting 1 file containing '{stac_suffix_string}' in {burst_static_layer_s3_subpath}, found {len(s3_static_layer_files)}: {s3_static_layer_files} "
            )
        else:
            static_layer_stac_file = s3_static_layer_files[0]
            logger.info(f"Static layer stac item found: {static_layer_stac_file}")

        burst_static_layer_stac_url = f"https://{self.s3_bucket}.s3.{self.s3_region}.amazonaws.com/{static_layer_stac_file}"

        logger.info(f"Static layer url: {burst_static_layer_stac_url}")

        try:
            # Send HTTP GET request
            response = requests.get(burst_static_layer_stac_url)
            # Raise an error if the request failed
            response.raise_for_status()
        except requests.exceptions.RequestException as e:
            raise RuntimeError(
                f"Failed to fetch static layer STAC metadata from '{burst_static_layer_stac_url}'. "
                f"Ensure the RTC_S1_STATIC product exists at this location."
                f"Request error: {e}"
            ) from e

        # add the link to the static layer metadata file to the links
        self.item.add_link(
            pystac.Link(
                rel="static-layers-stac-item",
                target=burst_static_layer_stac_url,
                media_type=pystac.media_type.STAC_JSON,
            )
        )

        static_layer_browse_url = (
            f"https://{self.s3_bucket}.s3.{self.s3_region}.amazonaws.com"
            f"/index.html?prefix={burst_static_layer_s3_subpath}"
        )

        # add link to browse the static layer folder
        self.item.add_link(
            pystac.Link(
                rel="static-layers-browse",
                target=static_layer_browse_url,
                media_type=pystac.media_type.MediaType.HTML,
            )
        )

        # Load the JSON content into a Python dictionary
        burst_static_layer_stac = response.json()

        # iterate through the static layer assets and add them to the file
        for asset_title in burst_static_layer_stac["assets"].keys():

            # data for each asset
            asset_data = burst_static_layer_stac["assets"][asset_title]

            # extra fields data is everything with the asset but these
            excl = ["href", "description", "roles", "type"]

            extra_fields = asset_data.copy()
            for key in excl:
                extra_fields.pop(key)  # `None` prevents error if key doesn't exist

            self.item.add_asset(
                asset_title,
                pystac.asset.Asset(
                    href=asset_data["href"],
                    title=asset_title,
                    description=asset_data["description"],
                    roles=asset_data["roles"],
                    media_type=asset_data["type"],
                    extra_fields=extra_fields,
                ),
            )

    def save(self, save_path: str | Path = "metadata.json"):
        """save the STAC item to a file

        Parameters
        ----------
        save_path : str
            Path to save the file. default 'metadata.json'.
        """
        with open(save_path, "w") as fp:
            json.dump(self.item.to_dict(), fp)
