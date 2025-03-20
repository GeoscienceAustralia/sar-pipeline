import json
from pathlib import Path
from typing import Optional, List
import rasterio
import pystac
from pystac.extensions import sar, raster
from pystac.validation import validate
from pystac import Item
from shapely.geometry import shape
from datetime import datetime
from dateutil.parser import isoparse
import numpy as np

from sar_pipeline.aws.metadata.h5 import H5Manager
from sar_pipeline.utils.spatial import polygon_str_to_geojson

import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

REQUIRED_ASSET_FILETYPES = [
    "_mask.tif",
    "_number_of_looks.tif",
    "_rtc_anf_gamma0_to_beta0.tif",
    "_rtc_anf_gamma0_to_sigma0.tif",
    "_HH.tif",
    "_HV.tif",
    "_VV.tif",
    "_VH.tif",
    "_local_incidence_angle.tif",
    "_incidence_angle.tif",
    "_interpolated_dem.tif",
    ".png",
]

ASSET_FILETYPE_TO_TITLE = {
    "_mask.tif": "mask",
    "_number_of_looks.tif": "number_of_looks",
    "_rtc_anf_gamma0_to_beta0.tif": "gamma0_to_beta0_ratio",
    "_rtc_anf_gamma0_to_sigma0.tif": "gamma0_to_sigma0_ratio",
    "_HH.tif": "HH",
    "_HV.tif": "HV",
    "_VV.tif": "VV",
    "_VH.tif": "VH",
    "_local_incidence_angle.tif": "local_incidence_angle",
    "_incidence_angle.tif": "incidence_angle",
    "_interpolated_dem.tif": "digital_elevation_model",
    ".png": "thumbnail",
}

ASSET_FILETYPE_TO_DESCRIPTION = {
    "_mask.tif": "shadow layover data mask",
    "_number_of_looks.tif": "number of looks",
    "_rtc_anf_gamma0_to_beta0.tif": "backscatter conversion layer, gamma0 to beta0. Eq. beta0 = rtc_anf_gamma0_to_beta0*gamma0",
    "_rtc_anf_gamma0_to_sigma0.tif": "backscatter conversion layer, gamma0 to sigma0. Eq. sigma0 = rtc_anf_sigma0_to_sigma0*gamma0",
    "_HH.tif": "HH polarised backscatter",
    "_HV.tif": "HV polarised backscatter",
    "_VV.tif": "VV polarised backscatter",
    "_VH.tif": "VH polarised backscatter",
    "_local_incidence_angle.tif": "local incidence angle (LIA)",
    "_incidence_angle.tif": "incidence angle (IA)",
    "_interpolated_dem.tif": "interpolated digital elevation model (DEM)",
    ".png": "thumbnail image for backscatter",
}

ASSET_FILETYPE_TO_ROLES = {
    "_mask.tif": ["data", "ancillary", "mask", "shadow", "layover"],
    "_number_of_looks.tif": ["data", "ancillary"],
    "_rtc_anf_gamma0_to_beta0.tif": ["data", "ancillary", "conversion"],
    "_rtc_anf_gamma0_to_sigma0.tif": ["data", "ancillary", "conversion"],
    "_HH.tif": ["data", "backscatter"],
    "_HV.tif": ["data", "backscatter"],
    "_VV.tif": ["data", "backscatter"],
    "_VH.tif": ["data", "backscatter"],
    "_local_incidence_angle.tif": ["data", "ancillary"],
    "_incidence_angle.tif": ["data", "ancillary"],
    "_interpolated_dem.tif": ["data", "ancillary"],
    ".png": ["thumbnail"],
}

ASSET_FILETYPE_TO_MEDIATYPE = {
    "_mask.tif": pystac.media_type.MediaType.COG,
    "_number_of_looks.tif": pystac.media_type.MediaType.COG,
    "_rtc_anf_gamma0_to_beta0.tif": pystac.media_type.MediaType.COG,
    "_rtc_anf_gamma0_to_sigma0.tif": pystac.media_type.MediaType.COG,
    "_HH.tif": pystac.media_type.MediaType.COG,
    "_HV.tif": pystac.media_type.MediaType.COG,
    "_VV.tif": pystac.media_type.MediaType.COG,
    "_VH.tif": pystac.media_type.MediaType.COG,
    "_local_incidence_angle.tif": pystac.media_type.MediaType.COG,
    "_incidence_angle.tif": pystac.media_type.MediaType.COG,
    "_interpolated_dem.tif": pystac.media_type.MediaType.COG,
    ".png": pystac.media_type.MediaType.PNG,
}


class BurstH5toStacManager:
    """utility class to convert burst .h5 metadata to a STAC data item data"""

    def __init__(
        self,
        h5_filepath: Path,
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
        self.collection = collection
        self.stac_extensions = [
            "https://stac-extensions.github.io/product/v0.1.0/schema.json",
            "https://github.com/stac-extensions/projection",
            "https://stac-extensions.github.io/sat/v1.1.0/schema.json",
            "https://stac-extensions.github.io/sar/v1.1.0/schema.json",
            "https://stac-extensions.github.io/sentinel-1/v0.2.0/schema.json",
            "https://stac-extensions.github.io/processing/v1.2.0/schema.json",
            "https://stac-extensions.github.io/card4l/v0.1.0/sar/product.json",
            "https://stac-extensions.github.io/storage/v2.0.0/schema.json",
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
        self.geometry_4326 = polygon_str_to_geojson(
            self.h5.search_value("boundingPolygon")
        )
        self.bbox_4326 = shape(self.geometry_4326["geometry"]).bounds
        self.burst_id = self.h5.search_value("burstID")
        self.burst_s3_subfolder = f"{self.s3_project_folder}/{self.collection}/{self.start_dt.year}/{self.start_dt.month}/{self.start_dt.day}/{self.burst_id}"
        self.bucket_href = (
            f"https://{self.s3_bucket}.s3.{self.s3_region}.amazonaws.com//"
        )
        self.base_href = Path(self.bucket_href) / self.burst_s3_subfolder

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
        self.item.properties["product:type"] = "NRB"  # or RTC ?
        self.item.properties["product:timeliness"] = ""  # NRT etc see docs

        # add projection (proj) stac extension properties
        self.item.properties["proj:epsg"] = self.h5.search_value("data/projection")
        self.item.properties["proj:bbox"] = self.h5.search_value("boundingBox")

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
        self.item.properties["sat:orbit_state_vectors"] = ""  # map this from .h5

        # add the sar stac extension properties - see specs to add more
        self.item.properties["sar:instrument_mode"] = self.h5.search_value(
            "acquisitionMode"
        )
        self.item.properties["sar:frequency_band"] = self.h5.search_value("radarBand")
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

        # add sentinel-1 stac extension properties - https://github.com/stac-extensions/sentinel-1
        self.item.properties["s1:orbit_source"] = self.h5.search_value("orbitType")

        # add processing stac extension specification
        self.item.properties["processing:lineage"] = ""
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

        # add card4l stac extension properties - NOTE this may be updated with CEOS-ARD stac
        self.item.properties["card4l:specification"] = "NRB"
        self.item.properties["card4l:specification_version"] = 5.5
        self.item.properties["card4l:noise_removal_applied"] = self.h5.search_value(
            "noiseCorrectionApplied"
        )
        self.item.properties["card4l:speckle_filtering"] = self.h5.search_value(
            "filteringApplied"
        )
        self.item.properties["card4l:pixel_coordinate_convention"] = "Area"
        self.item.properties["card4l:measurement_type"] = self.h5.search_value(
            "outputBackscatterNormalizationConvention"
        )
        self.item.properties["card4l:measurement_convention"] = self.h5.search_value(
            "outputBackscatterExpressionConvention"
        )
        self.item.properties["card4l:conversion_eq"] = self.h5.search_value(
            "outputBackscatterDecibelConversionEquation"
        )
        self.item.properties["card4l:northern_geometric_accuracy"] = {
            "bias": self.h5.search_value(
                "geometricAccuracy/bias/y"
            ),  # NOTE not north in 3031
            "std": self.h5.search_value(
                "geometricAccuracy/stddev/y"
            ),  # NOTE not north in 3031
        }
        self.item.properties["card4l:eastern_geometric_accuracy"] = {
            "bias": self.h5.search_value(
                "geometricAccuracy/bias/x"
            ),  # NOTE not north in 3031
            "std": self.h5.search_value(
                "geometricAccuracy/stddev/x"
            ),  # NOTE not north in 3031
        }
        self.item.properties["card4l:gridding_convention"] = (
            "geocoded burst",
        )  # TODO is this a valid value to set?

        # add the storage stac extension properties
        self.item.properties["storage:type"] = "aws-s3"
        self.item.properties["storage:platform"] = (
            f"https://{self.s3_bucket}.s3.{self.s3_region}"
        )
        self.item.properties["storage:region"] = f"{self.s3_region}"
        self.item.properties["requester_pays"] = False

    def add_links_from_h5(self):
        """add links to the stac item from the .h5 file"""

        # link to the source SLC
        self.item.add_link(
            pystac.Link(
                rel="derived_from",
                target=str(
                    self.base_href / self.h5.search_value("sourceData/dataAccess")
                ),
                media_type=pystac.media_type.MediaType.JSON,
            )
        )

        # link to the .h5 file containing additional metadata
        self.item.add_link(
            pystac.Link(
                rel="metadata",
                target=str(self.base_href / self.h5_filepath.name),
                # media_type=
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
                target=str(self.base_href / filename),
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
        IGNORE_ASSETS = [
            f"_{p}.tif"
            for p in ["HH", "HV", "VV", "VH"]
            if p not in self.item.properties["sar:polarizations"]
        ]
        INCLUDED_ASSET_FILETYPES = [
            x for x in REQUIRED_ASSET_FILETYPES if x not in IGNORE_ASSETS
        ]

        # iterate through the included/required assets and add to STAC item
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
                    asset_shape = r.shape
                    asset_transform = list(r.transform)

            # add the asset to the STAC item
            self.item.add_asset(
                asset_title,
                pystac.asset.Asset(
                    href=str(self.base_href / asset_filepath.name),
                    title=asset_title,
                    description=asset_description,
                    roles=asset_roles,
                    media_type=asset_mediatype,
                    extra_fields={
                        "proj:shape": asset_shape,
                        "proj:transform": asset_transform,
                    },
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
