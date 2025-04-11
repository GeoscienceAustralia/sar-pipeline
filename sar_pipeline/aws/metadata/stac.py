import json
from pathlib import Path
from typing import Literal
import rasterio
import pystac
from shapely.geometry import shape
from dateutil.parser import isoparse
import requests
import datetime
import re
import numpy as np

from sar_pipeline.aws.metadata.h5 import H5Manager
from sar_pipeline.utils.spatial import polygon_str_to_geojson, convert_bbox
from sar_pipeline.aws.metadata.filetypes import (
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
    """utility class to convert burst .h5 metadata to a STAC data item data"""

    def __init__(
        self,
        h5_filepath: Path,
        product: str,
        collection: str,
        s3_bucket: str,
        s3_project_folder: str,
        s3_region: str = "ap-southeast-2",
    ):
        """
        Parameters
        ----------
        h5_filepath : Path
            Local path to the .h5 file output from the opera/RTC process
        product: str
            The product being made. RTC_S1 or RTC_S1_STATIC
        collection : str
            The collection the product belongs to. e.g. s1_rtc_c1
        s3_bucket : str
            The S3 bucket where data will be uploaded
        s3_project_folder : str
            The project folder in the S3 bucket if required. Note that
            the collection will be appended to this folder path.
        s3_region : str, optional
            The region of the S3 bucket, by default "ap-southeast-2"
        """
        self.h5_filepath = h5_filepath
        self.h5 = H5Manager(self.h5_filepath)  # class to help get values from .h5 file
        self.id = self.h5_filepath.stem
        self.product = self._check_valid_product(product)
        self.collection = collection
        self.stac_extensions = [
            "https://stac-extensions.github.io/product/v0.1.0/schema.json",
            "https://stac-extensions.github.io/sar/v1.1.0/schema.json",
            "https://stac-extensions.github.io/altimetry/v0.1.0/schema.json",
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
        self.projection = self.h5.search_value("data/projection")
        if self.product == "RTC_S1":
            self.geometry_4326 = polygon_str_to_geojson(
                self.h5.search_value("boundingPolygon")
            )
            self.bbox_4326 = shape(self.geometry_4326["geometry"]).bounds
        elif self.product == "RTC_S1_STATIC":
            # 4326 needs to be converted from native coordinates
            self.bbox_4326 = convert_bbox(
                self.h5.search_value("boundingBox"),
                src_crs=self.projection,
                trg_crs=4326,
            )
            # geometry is not included, set this to be bbox
            self.geometry_4326 = self.bbox_4326

        self.burst_id = self.h5.search_value("burstID")
        self.burst_s3_subfolder = self._make_s3_subfolder()
        self.bucket_href = f"https://{self.s3_bucket}.s3.{self.s3_region}.amazonaws.com"
        self.base_href = f"{self.bucket_href}/{self.burst_s3_subfolder}"

    def _check_valid_product(self, product):
        "check the product is valid"
        if product not in ["RTC_S1", "RTC_S1_STATIC"]:
            raise ValueError("Invalid product")
        return product

    def _make_s3_subfolder(self):
        "make the s3 subfolder destination based on the product"
        if self.product == "RTC_S1":
            # include acquisition dates for S1_RTC
            return f"{self.s3_project_folder}/{self.collection}/{self.burst_id}/{self.start_dt.year}/{self.start_dt.month}/{self.start_dt.day}"
        if self.product == "RTC_S1_STATIC":
            # static products are date independent
            return f"{self.s3_project_folder}/{self.collection}/{self.burst_id}"
        else:
            raise ValueError()

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
            "instruments": self.h5.search_value("instrumentName"),
            "created": self.h5.search_value("identification/processingDateTime"),
        }

        self.item = pystac.Item(
            id=self.id,
            geometry=self.geometry_4326,
            bbox=self.bbox_4326,
            datetime=self.start_dt,
            start_datetime=self.start_dt,
            end_datetime=self.end_dt,
            collection=self.collection,
            properties=base_properties,
            stac_extensions=self.stac_extensions,
        )

    def add_properties_from_h5(self):
        """Map required properties from the .h5 file"""

        # TODO finalise stac properties based on best practice
        # add product stac extension properties
        self.item.properties["product:type"] = self.product
        self.item.properties["product:timeliness_category"] = (
            self._get_product_timeliness_category(self.start_dt, self.processed_dt)
        )

        # add ceos-ard stac extension properties
        if self.product == "RTC_S1":
            self.item.properties["ceosard:type"] = "NRB"
            self.item.properties["ceosard:specification"] = (
                "Synthetic Aperture Radar (CEOS-ARD SAR)"
            )
            self.item.properties["ceosard:specification_version"] = "1.1"

        # add projection (proj) stac extension properties
        self.item.properties["proj:epsg"] = self.projection
        self.item.properties["proj:bbox"] = self.h5.search_value("boundingBox")

        # add the sar stac extension properties
        self.item.properties["sar:frequency_band"] = self.h5.search_value("radarBand")
        if self.product == "RTC_S1":
            self.item.properties["sar:center_frequency"] = self.h5.search_value(
                "centerFrequency"
            )
            self.item.properties["sar:polarizations"] = self.h5.search_value(
                "listOfPolarizations"
            )
        self.item.properties["sar:observation_direction"] = self.h5.search_value(
            "lookDirection"
        )
        self.item.properties["sar:relative_burst"] = self.h5.search_value("burstID")
        self.item.properties["sar:beam_ids"] = self.h5.search_value("subSwathID")

        # add altimetry stac extension properties
        self.item.properties["altm:instrument_type"] = "sar"
        self.item.properties["altm:instrument_mode"] = self.h5.search_value(
            "acquisitionMode"
        )

        # add sat stac extension properties
        self.item.properties["sat:orbit_state"] = self.h5.search_value(
            "orbitPassDirection"
        )
        self.item.properties["sat:absolute_orbit"] = self.h5.search_value(
            "absoluteOrbitNumber"
        )
        self.item.properties["sat:relative_orbit"] = "trackNumber"
        self.item.properties["sat:orbit_cycle"] = "12"
        self.item.properties["sat:osv"] = self.h5.search_value(
            "orbitFiles"
        )  # Link to a file containing the orbit state vectors.
        self.item.properties["sat:orbit_state_vectors"] = ""  # TODO map this from .h5

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
        self.item.properties["processing:version"] = self.h5.search_value(
            "identification/productVersion"
        )
        self.item.properties["processing:software"] = {
            "isce3": self.h5.search_value("algorithms/isce3Version"),
            "s1Reader": self.h5.search_value("algorithms/s1ReaderVersion"),
            "OPERA-adt/RTC": self.h5.search_value("algorithms/softwareVersion"),
            "sar-pipeline": "",  # TODO get from __version__
            "dem-handler": "",  # TODO get from __version__
        }

        # proposed sar-ard stac extension properties
        self.item.properties["sar-ard:source_id"] = self.h5.search_value(
            "l1SlcGranules"
        )
        self.item.properties["sar-ard:pixel_spacing_x"] = abs(
            self.h5.search_value("xCoordinateSpacing")
        )
        self.item.properties["sar-ard:pixel_spacing_y"] = abs(
            self.h5.search_value("yCoordinateSpacing")
        )
        self.item.properties["sar-ard:resolution_x"] = abs(
            self.h5.search_value("xCoordinateSpacing")
        )
        self.item.properties["sar-ard:resolution_y"] = abs(
            self.h5.search_value("yCoordinateSpacing")
        )
        self.item.properties["sar-ard:speckle_filter_applied"] = self.h5.search_value(
            "filteringApplied"
        )
        self.item.properties["sar-ard:speckle_filter_type"] = ""
        self.item.properties["sar-ard:speckle_filter_window"] = ()
        self.item.properties["sar-ard:measurement_type"] = self.h5.search_value(
            "outputBackscatterNormalizationConvention"
        )
        self.item.properties["sar-ard:measurement_convention"] = self.h5.search_value(
            "outputBackscatterExpressionConvention"
        )
        self.item.properties["sar-ard:conversion_eq"] = self.h5.search_value(
            "outputBackscatterDecibelConversionEquation"
        )
        if self.product == "RTC_S1":
            self.item.properties["sar-ard:noise_removal_applied"] = (
                self.h5.search_value("noiseCorrectionApplied")
            )

        # additional non required parameters for atmosphere that would be good to have
        self.item.properties["sar-ard:static_tropospheric_correction_applied"] = (
            self.h5.search_value("staticTroposphericGeolocationCorrectionApplied")
        )
        self.item.properties["sar-ard:wet_tropospheric_correction_applied"] = (
            self.h5.search_value("wetTroposphericGeolocationCorrectionApplied")
        )
        self.item.properties["sar-ard:bistatic_correction_applied"] = (
            self.h5.search_value("bistaticDelayCorrectionApplied")
        )
        self.item.properties["sar-ard:ionospheric_correction_applied"] = False

        # TODO fill with study result values
        self.item.properties["sar-ard:geometric_accuracy_ALE"] = "TODO"
        self.item.properties["sar-ard:geometric_accuracy_rmse"] = "TODO"
        self.item.properties["sar-ard:geometric_accuracy_range"] = "TODO"
        self.item.properties["sar-ard:geometric_accuracy_azimuth"] = "TODO"

        # add the storage stac extension properties
        self.item.properties["storage:type"] = "aws-s3"
        self.item.properties["storage:platform"] = (
            f"https://{self.s3_bucket}.s3.{self.s3_region}"
        )
        self.item.properties["storage:region"] = f"{self.s3_region}"
        self.item.properties["storage:requester_pays"] = False

    def add_fixed_links(self):
        """add fixed links that are not expected to change frequently"""

        # link to the ceos-ard product family specification
        self.item.add_link(
            pystac.Link(
                rel="ceos-ard-specification",
                target="https://ceos.org/ard/files/PFS/SAR/v1.1/CEOS-ARD_PFS_Synthetic_Aperture_Radar_v1.1.pdf",
                media_type=pystac.media_type.MediaType.PDF,
            )
        )

        # add the link the the EGM_08 GEOID
        self.item.add_link(
            pystac.Link(
                rel="geoid-source",
                target="https://aria-geoid.s3.us-west-2.amazonaws.com/us_nga_egm2008_1_4326__agisoft.tif",
            )
        )

    def add_dynamic_links_from_h5(self):
        """add links to the stac item from the .h5 file"""

        # link to the source SLC
        self.item.add_link(
            pystac.Link(
                rel="derived_from",
                target=self.h5.search_value("sourceData/dataAccess"),
            )
        )

        # Add link to the DEM
        self.item.add_link(
            pystac.Link(
                rel="dem-source",
                target=self.h5.search_value("demSource"),
            )
        )

        # Add link to the RTC algorithm, get it from the reference
        ref_text = self.h5.search_value(
            "radiometricTerrainCorrectionAlgorithmReference"
        )
        self.item.add_link(
            pystac.Link(
                rel="rtc-algorithm",
                target=self._extract_doi_link(ref_text),
            )
        )

        # Add link to the geocoding algorithm, get it from the reference
        ref_text = self.h5.search_value("geocodingAlgorithmReference")
        self.item.add_link(
            pystac.Link(
                rel="geocoding-algorithm",
                target=self._extract_doi_link(ref_text),
            )
        )

        # Add link to the noise removal, get it from the reference
        if self.product == "RTC_S1":
            ref_text = self.h5.search_value("noiseCorrectionAlgorithmReference")
            self.item.add_link(
                pystac.Link(
                    rel="noise-correction",
                    target=self._extract_http_link(ref_text),
                )
            )

        # link to the .h5 file containing additional metadata
        self.item.add_link(
            pystac.Link(
                rel="metadata",
                target=f"{self.base_href}/{self.h5_filepath.name}",
            )
        )

    def add_self_link(self, filename: str | Path):
        """Add the self / STAC metadata link to the stac item

        Parameters
        ----------
        filename : str | Path
            Filename of the STAC file. This will be appended to the
            base_href for product.
        """

        self.item.add_link(
            pystac.Link(
                rel="self",
                target=f"{self.base_href}/{filename}",
                media_type=pystac.media_type.MediaType.JSON,
            )
        )

    def add_assets_from_folder(self, burst_folder: Path):
        """Add the asset files from the burst folder

        Parameters
        ----------
        burst_folder : Path
            path to the local folder containing output products for a single burst.
            e.g. /path/to/my/scene_burst/t070_149813_iw2

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
            pols = self.item.properties["sar:polarizations"]
        elif self.product == "RTC_S1_STATIC":
            pols = []  # no pol for static products, only auxiliary files
        IGNORE_ASSETS = [f"_{p}.tif" for p in ["HH", "HV", "VV", "VH"] if p not in pols]
        INCLUDED_ASSET_FILETYPES = [
            x for x in REQUIRED_ASSET_FILETYPES[self.product] if x not in IGNORE_ASSETS
        ]

        # iterate through the included/required assets and add to the STAC item
        for asset_filetype in INCLUDED_ASSET_FILETYPES:
            # map the asset_filetype to important parameters
            asset_title = ASSET_FILETYPE_TO_TITLE[asset_filetype]
            asset_description = ASSET_FILETYPE_TO_DESCRIPTION[asset_filetype]
            asset_roles = ASSET_FILETYPE_TO_ROLES[asset_filetype]
            asset_mediatype = ASSET_FILETYPE_TO_MEDIATYPE[asset_filetype]
            asset_filepaths = [
                x for x in burst_files if x.name == f"{self.id}{asset_filetype}"
            ]
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
                    extra_fields = {
                        "proj:shape": r.shape,
                        "proj:transform": list(r.transform),
                        "proj:epsg": r.crs.to_epsg(),
                        "raster:data_type": r.dtypes[0],
                        "raster:sampling": r.tags().get("AREA_OR_POINT", ""),
                        "raster:nodata": (
                            r.nodata
                            if (
                                isinstance(r.nodata, (float, int))
                                and not np.isnan(r.nodata)
                            )
                            else str(r.nodata)
                        ),
                    }
                    if asset_filetype == "_mask.tif":
                        extra_fields["raster:values"] = {
                            "shadow": 1,
                            "layover": 2,
                            "shadow_and_layover": 3,
                        }
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

    def add_linked_static_layer_assets(self):

        burst_id = self.item.properties["sar:relative_burst"]

        static_layer_url = self.h5.search_value("staticLayersDataAccess")
        burst_static_layer_stac_url = f"{static_layer_url}/{burst_id}/metadata.json"

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

        # Load the JSON content into a Python dictionary
        burst_static_layer_stac = response.json()

        # iterate through the static layer assets and add them
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
