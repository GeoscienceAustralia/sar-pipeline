import os
from pathlib import Path
from typing import Literal
import json
from shapely.geometry import shape, mapping, Polygon, MultiPolygon
import pystac
from datetime import datetime
from dateutil.parser import isoparse
import sar_pipeline
import dem_handler
import rasterio
import numpy as np
import re

from sar_pipeline.preparation.downloads.scenes import (
    query_scene_from_cdse,
    NonSingleSceneResultError,
)

from sar_pipeline.utils.sentinel1 import extract_metadata_from_s1_id

from sar_pipeline.utils.spatial import (
    get_valid_data_min_rect_polygon_from_tif,
    get_data_crs_and_resolution_from_tif,
)

from sar_pipeline.utils.antimeridian import (
    check_shape_crosses_antimeridian,
    get_bounds_for_antimeridian_shape,
    convert_antimeridian_polygon_to_multipolygon,
)

from sar_pipeline.pipelines.pyrosar_gamma.metadata.odc import (
    get_odc_product_name,
    make_gamma_rtc_s1_product_s3_prefix,
)

from sar_pipeline.pipelines.pyrosar_gamma.metadata.filetypes import (
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

pol_str_to_list = {
    "SH": ["HH"],
    "SV": ["VV"],
    "DH": ["HH", "HV"],
    "DV": ["VV", "VH"],
}


class GammaNRBtoSTAC:
    """utility to create a stac document from pyroSAR-GAMMA outputs"""

    def __init__(
        self,
        scene_id: Path,
        product_folder: Path,
        backscatter_convention: Literal["gamma0", "sigma0", "beta0"],
        collection_number: int,
        s3_bucket: str,
        s3_project_folder: str,
        s3_region: str = "ap-southeast-2",
    ):
        # set input variables
        self.scene_id = scene_id
        self.product_folder = product_folder
        self.backscatter_convention = backscatter_convention
        self.collection_number = collection_number
        self.s3_bucket = s3_bucket
        self.s3_project_folder = s3_project_folder
        self.s3_region = s3_region
        # get the source scene metadata from the cdse
        self.scene_src_metadata = self._get_scene_metadata_from_cdse(scene_id)
        # get additional attributes that contain information about acquisition
        self.scene_attributes = self.scene_src_metadata["Attributes"][0]
        self.all_scene_attributes = self.scene_src_metadata["Attributes"]
        self.geometry_4326 = self.scene_src_metadata["GeoFootprint"]
        self.start_dt = isoparse(self.scene_src_metadata["ContentDate"]["Start"])
        self.end_dt = isoparse(self.scene_src_metadata["ContentDate"]["End"])
        self.created_dt = datetime.now()
        self.bbox_4326 = shape(self.geometry_4326).bounds
        # get the geometry and bbox from an actual tif in tif crs
        self.geometry, self.bbox, self.crs, self.resolution = (
            self._get_metadata_from_tif()
        )
        # handle the antimeridian
        if check_shape_crosses_antimeridian(
            shape(self.geometry_4326), max_antimeridian_crossing_degrees=40
        ):
            logger.warning(f"STAC geometry crosses the antimeridian. reformatting")
            self._handle_antimeridian_crossing()

        # get the scene metadata from the id
        self.scene_metadata = extract_metadata_from_s1_id(scene_id)
        self.polarisations = pol_str_to_list[self.scene_metadata.polarisation]
        self.acquisition_mode = self.scene_metadata.mode_beam
        # get the odc product name
        self.odc_product_name = get_odc_product_name(
            product="RTC_S1",
            collection_number=1,
            polarisations=self.polarisations,
            acquisition_mode=self.acquisition_mode.lower(),
        )
        self.s3_product_folder = make_gamma_rtc_s1_product_s3_prefix(
            s3_project_folder=s3_project_folder,
            collection_number=self.collection_number,
            polarisations=self.polarisations,
            acquisition_mode=self.acquisition_mode,
            scene_id=self.scene_id,
            start_dt=self.start_dt,
        )
        # stac extensions
        self.stac_extensions = [
            "https://stac-extensions.github.io/classification/v2.0.0/schema.json",
            "https://stac-extensions.github.io/product/v0.1.0/schema.json",
            "https://stac-extensions.github.io/sar/v1.1.0/schema.json",
            "https://stac-extensions.github.io/projection/v2.0.0/schema.json",
            "https://stac-extensions.github.io/raster/v2.0.0/schema.json",
            "https://stac-extensions.github.io/sat/v1.1.0/schema.json",
            "https://stac-extensions.github.io/sentinel-1/v0.2.0/schema.json",
            "https://stac-extensions.github.io/processing/v1.2.0/schema.json",
            "https://stac-extensions.github.io/storage/v2.0.0/schema.json",
        ]
        self.bucket_href = f"https://{self.s3_bucket}.s3.{self.s3_region}.amazonaws.com"
        self.base_href = f"{self.bucket_href}/{self.s3_product_folder}"

    def _get_scene_metadata_from_cdse(self, scene_id):
        query_results = query_scene_from_cdse(scene_id, expand_attributes=True)
        if len(query_results) != 1:
            raise NonSingleSceneResultError(
                f"Expected 1 scene, found {len(query_results)} results for scene id : {scene_id}. Check input scene."
            )
        else:
            return query_results[0]

    def _get_tif_file_name(self):
        """get the tif file name for the backscatter convention"""

        matches = [
            p
            for p in Path(self.product_folder).rglob("*.tif")
            if f"{self.backscatter_convention}" in p.name.lower()
        ]

        if not matches:
            raise FileNotFoundError(
                f"Could not find {self.backscatter_convention} .tif file in product folder : {self.product_folder}"
            )

        return matches[0]

    def _get_metadata_from_tif(self):
        """get the geometry and bbox in tif crs from a tif"""
        tif_file = self._get_tif_file_name()
        geometry = get_valid_data_min_rect_polygon_from_tif(tif_file, n_segments=5)
        bbox = geometry.bounds
        crs, res = get_data_crs_and_resolution_from_tif(tif_file)
        return geometry, bbox, crs, res

    def get_output_filename_prefix(self):
        tif_file = self._get_tif_file_name()
        pattern = r"\d{8}T\d{6}"
        match_last_idx = re.search(pattern, tif_file.name).span()[1]
        return tif_file.name[:match_last_idx]

    def _get_attribute_by_name(self, name):
        """ "This helper function extracts values from the CDSE metadata. e.g. 'orbitDirection'"""
        for attribute in self.all_scene_attributes:
            if attribute["Name"] == name:
                return attribute["Value"]
        return None

    def _handle_antimeridian_crossing(self):
        """Correct the geometries for STAC at the antimeridian"""
        corrected_bounds = get_bounds_for_antimeridian_shape(shape(self.geometry_4326))
        logger.info(f"Old bounds : {self.bbox_4326}")
        logger.info(f"New bounds : {corrected_bounds}")
        self.bbox_4326 = corrected_bounds
        if isinstance(shape(self.geometry_4326), Polygon):
            corrected_geometry = convert_antimeridian_polygon_to_multipolygon(
                shape(self.geometry_4326)
            )
            logger.info(f"Old geometry : {shape(self.geometry_4326)}")
            logger.info(f"New geometry : {corrected_geometry}")
            self.geometry_4326 = mapping(corrected_geometry)
        elif isinstance(shape(self.geometry_4326), MultiPolygon):
            logger.info(
                f"Antimeridian geometry is already multipolygon, assuming correct : {shape(self.geometry_4326)}"
            )

    def make_stac_item(self):
        """Make a pystac.item.Item for the given burst using key properties."""

        # Some base properties need to be defined
        base_properties = {
            "gsd": self.resolution,
            "constellation": "Sentinel-1",
            "platform": self.scene_metadata.mission,
            "instruments": ["SENTINEL-1A CSAR"],
            "created": str(self.created_dt),
        }

        self.item = pystac.Item(
            id=self.scene_id,
            geometry=self.geometry_4326,
            bbox=self.bbox_4326,
            datetime=self.start_dt,
            start_datetime=self.start_dt,
            end_datetime=self.end_dt,
            collection=self.odc_product_name,
            properties=base_properties,
            stac_extensions=self.stac_extensions,
        )

    def add_properties(self):
        """Map required properties."""

        # add odc specific fields
        self.item.properties["odc:product"] = (
            self.odc_product_name
        )  # this needs to  dynamic based on the pol files and match odc product
        self.item.properties["odc:product_family"] = "sar_ard"
        self.item.properties["odc:region_code"] = self._get_attribute_by_name(
            "relativeOrbitNumber"
        )
        self.item.properties["odc:producer"] = "ga.gov.au"
        self.item.properties["odc:dataset_version"] = "0.1.0"

        # add dea dataset maturity can be ["final", "interim", "nrt"]
        self.item.properties["dea:dataset_maturity"] = "interim"

        # add product stac extension properties
        self.item.properties["product:type"] = "NRB"
        # remove timeliness as not required. May re-add if approach is determined.
        # self.item.properties["product:timeliness"] = ""
        # self.item.properties["product:timeliness_category"] = (
        #     self._get_product_timeliness_category(self.start_dt, self.processed_dt)
        # )

        # add ceos-ard stac extension properties
        self.item.properties["ceosard:type"] = "radar"
        self.item.properties["ceosard:specification"] = "NRB"
        self.item.properties["ceosard:specification_version"] = "5.5"

        # add projection (proj) stac extension properties
        self.item.properties["proj:code"] = f"EPSG:{self.crs}"
        self.item.properties["proj:bbox"] = self.bbox

        # add the sar stac extension properties
        self.item.properties["sar:frequency_band"] = "C"
        self.item.properties["sar:center_frequency"] = 5.40500045433435  # GHz
        self.item.properties["sarard:center_frequency_unit"] = "GHz"
        self.item.properties["sar:polarizations"] = self.polarisations
        # add as a string for odc explorer
        self.item.properties["sarard:polarization_mode"] = "+".join(self.polarisations)
        self.item.properties["sar:observation_direction"] = "right"
        # self.item.properties["sar:beam_ids"] = [self.h5.search_value("subSwathID")]
        self.item.properties["sar:instrument_mode"] = self.acquisition_mode

        # add sat stac extension properties
        self.item.properties["sat:orbit_state"] = self._get_attribute_by_name(
            "orbitDirection"
        )
        self.item.properties["sat:absolute_orbit"] = self._get_attribute_by_name(
            "orbitNumber"
        )
        self.item.properties["sat:relative_orbit"] = self._get_attribute_by_name(
            "relativeOrbitNumber"
        )
        self.item.properties["sat:orbit_cycle"] = 12

        # # add sentinel-1 stac extension properties - https://github.com/stac-extensions/sentinel-1
        # self.item.properties["s1:orbit_source"] = self.h5.search_value("orbitType")

        # # add processing stac extension specification
        self.item.properties["processing:level"] = "Level-2"
        self.item.properties["processing:facility"] = "Geoscience Australia"
        self.item.properties["processing:datetime"] = str(self.created_dt)
        self.item.properties["processing:version"] = "0.1.0"
        self.item.properties["processing:software"] = {
            "GAMMA": Path(os.getenv("GAMMA_HOME", ".")).name,
            "sar-pipeline": sar_pipeline.__version__,
            "dem-handler": dem_handler.__version__,
        }

        # proposed sarard stac extension properties
        self.item.properties["sarard:source_id"] = self.scene_id + ".SAFE"
        # self.item.properties["sarard:source_geometry"] = "slant range"
        self.item.properties["sarard:scene_id"] = self.scene_id

        # self.item.properties["sarard:orbit_file"] = self.h5.search_value("orbitFiles")[
        #     0
        # ]  # Link to a file containing the orbit state vectors.
        self.item.properties["sarard:UL_longitude"] = self.bbox_4326[0]  # left
        self.item.properties["sarard:UL_latitude"] = self.bbox_4326[3]  # bottom
        self.item.properties["sarard:LR_longitude"] = self.bbox_4326[2]  # right
        self.item.properties["sarard:LR_latitude"] = self.bbox_4326[1]  # top
        self.item.properties["sarard:pixel_spacing_x"] = self.resolution
        self.item.properties["sarard:pixel_spacing_y"] = self.resolution
        self.item.properties["sarard:pixel_spacing_unit"] = "metre"
        self.item.properties["sarard:resolution_x"] = self.resolution
        self.item.properties["sarard:resolution_y"] = self.resolution
        self.item.properties["sarard:resolution_unit"] = "metre"
        self.item.properties["sarard:speckle_filter_applied"] = "FALSE"
        self.item.properties["sarard:speckle_filter_type"] = ""
        self.item.properties["sarard:speckle_filter_window"] = ()
        # convert to preferred format, gamma0 -> Gamma-0
        self.item.properties["sarard:measurement_type"] = {
            "gamma0": "Gamma-0",
            "sigma0": "Sigma-0",
            "beta0": "Beta-0",
        }[self.backscatter_convention]
        # self.item.properties["sarard:measurement_convention"] = self.h5.search_value(
        #     "outputBackscatterExpressionConvention"
        # )
        # self.item.properties["sarard:conversion_eq"] = self.h5.search_value(
        #     "outputBackscatterDecibelConversionEquation"
        # )
        # self.item.properties["sarard:noise_removal_applied"] = self.h5.search_value(
        #     "noiseCorrectionApplied"
        # )

        # additional non required parameters for atmosphere that would be good to have
        # self.item.properties["sarard:static_tropospheric_correction_applied"] = (
        #     self.h5.search_value("staticTroposphericGeolocationCorrectionApplied")
        # )
        # self.item.properties["sarard:wet_tropospheric_correction_applied"] = (
        #     self.h5.search_value("wetTroposphericGeolocationCorrectionApplied")
        # )
        # self.item.properties["sarard:bistatic_correction_applied"] = (
        #     self.h5.search_value("bistaticDelayCorrectionApplied")
        # )
        # self.item.properties["sarard:ionospheric_correction_applied"] = False

        # TODO when official document, link the study supporting these values
        # Northing and Easting error is based on surat basin CR's
        # self.item.properties["sarard:geometric_accuracy_absolute"] = 2.93
        # self.item.properties["sarard:geometric_accuracy_rmse"] = 3.08
        # self.item.properties["sarard:geometric_accuracy_north_bias"] = 2.25
        # self.item.properties["sarard:geometric_accuracy_east_bias"] = 1.14
        # self.item.properties["sarard:geometric_accuracy_north_std"] = 1.30
        # self.item.properties["sarard:geometric_accuracy_east_std"] = 1.19
        # self.item.properties["sarard:geometric_accuracy_unit"] = "metre"

        # add the timing information
        # self.item.properties["sarard:azimuth_time"] = str(
        #     self.azimuth_time.isoformat(timespec="microseconds").replace("+00:00", "Z")
        # )
        # self.item.properties["sarard:zero_doppler_start_time"] = str(
        #     self.zero_doppler_start_time.isoformat(timespec="microseconds").replace(
        #         "+00:00", "Z"
        #     )
        # )
        # self.item.properties["sarard:zero_doppler_end_time"] = str(
        #     self.zero_doppler_end_time.isoformat(timespec="microseconds").replace(
        #         "+00:00", "Z"
        #     )
        # )

        # add the storage stac extension properties
        self.item.properties["storage:schemes"] = {
            "aws": {
                "type": "aws-s3",
                "platform": "https://{bucket}.s3.{region}.amazonaws.com",
                "bucket": f"{self.s3_bucket}",
                "region": f"{self.s3_region}",
            }
        }

    def add_metadata_links(
        self,
        stac_filepath: Path | str,
    ):
        """Add:
            - Link to self / STAC metadata doc,

        This will be appended to the base_href for product.

        Parameters
        ----------
        stac_filepath : Path | str
            Filepath of the stac file

        """

        # the stac file gets referenced as self. We do not check if it
        # exists yet as it is saved after this process once all info as been added.
        self.item.add_link(
            pystac.Link(
                rel="self",
                target=f"{self.base_href}/{Path(stac_filepath).name}",
                media_type=pystac.media_type.STAC_JSON,
            )
        )

    def rename_asset_files(self):
        """Rename the assets in the output folder. Backscatter files will include the normalization
        convention type in the filename. Other assets renamed for clarity.
        """

        # get the list of files
        files = [x for x in Path(self.product_folder).iterdir()]

        for f in files:
            for old_suffix in RENAME_ASSET_FILETYPES.keys():
                new_suffix = RENAME_ASSET_FILETYPES[old_suffix]
                # logger.info(f'{str(f.name)}, {old_suffix_}, {new_suffix}')
                if str(f.name).endswith(old_suffix):
                    logger.info(f"renaming {old_suffix} -> {new_suffix}")
                    # backscatter convention will be added here
                    new_path = f.with_name(f.name.replace(old_suffix, new_suffix))
                    f.rename(new_path)
                    break  # once renamed, move to next file

    def add_assets(self, add_shape_transform_to_properties: bool = True):
        """Add the asset files from the local burst folder

        Parameters
        ----------
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
        asset_files = [x for x in Path(self.product_folder).iterdir()]
        pols = self.polarisations
        # Ignores the polarisations that are not included in the product.
        ignore_assets = [
            f"_{p}-{self.backscatter_convention}.tif"
            for p in ["HH", "HV", "VV", "VH"]
            if p not in pols
        ]
        # ignore the db files
        ignore_assets += [i.replace(".tif", "_db.tif") for i in ignore_assets]

        included_pol_assets = [f"_{p}-{self.backscatter_convention}.tif" for p in pols]
        required_asset_filetypes = REQUIRED_ASSET_FILETYPES[self.backscatter_convention]
        required_asset_filetypes = [
            f for f in required_asset_filetypes if f not in ignore_assets
        ]

        # iterate through the included/required assets and add to the STAC item
        for asset_filetype in required_asset_filetypes:
            # map the asset_filetype to important parameters
            asset_title = ASSET_FILETYPE_TO_TITLE[asset_filetype]
            asset_description = ASSET_FILETYPE_TO_DESCRIPTION[asset_filetype]
            asset_roles = ASSET_FILETYPE_TO_ROLES[asset_filetype]
            asset_mediatype = ASSET_FILETYPE_TO_MEDIATYPE[asset_filetype]
            asset_filepaths = [
                x for x in asset_files if str(x).endswith(asset_filetype)
            ]
            logger.info(f"{asset_filetype}")
            if len(asset_filepaths) == 0:
                raise FileNotFoundError(
                    f'The required asset: "{asset_filetype}" is missing from product folder: "{self.product_folder}"'
                )
            if len(asset_filepaths) > 1:
                raise ValueError(
                    f'Expected 1 file for asset: "{asset_filetype}", {len(asset_filepaths)} found in product folder: "{self.product_folder}"'
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
                        "data_type": r.dtypes[0],
                        "raster:sampling": raster_sampling,
                        "nodata": (
                            r.nodata
                            if (
                                isinstance(r.nodata, (float, int))
                                and not np.isnan(r.nodata)
                            )
                            else str(r.nodata)
                        ),
                    }

                    if asset_filetype == "_mask.tif":
                        # https://dep1doc.gfz-potsdam.de/attachments/download/393/Gamma_GEO_users_guide.pdf
                        extra_fields["classification:classes"] = [
                            {
                                "value": 0,
                                "name": "not_tested",
                            },
                            {
                                "value": 1,
                                "name": "tested",
                            },
                            {
                                "value": 2,
                                "name": "true_layover",
                            },
                            {
                                "value": 4,
                                "name": "layover",
                            },
                            {
                                "value": 8,
                                "name": "true_shadow",
                            },
                            {
                                "value": 16,
                                "name": "shadow",
                            },
                        ]
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
                        # add pixel coordinate convention
                        if "area" in raster_sampling:
                            self.item.properties[
                                "sarard:pixel_coordinate_convention"
                            ] = "pixel ULC"
                        elif "point" in raster_sampling:
                            self.item.properties[
                                "sarard:pixel_coordinate_convention"
                            ] = "pixel centre"

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

    def save(self, save_path: str | Path = "metadata.json"):
        """save the STAC item to a file

        Parameters
        ----------
        save_path : str
            Path to save the file. default 'metadata.json'.
        """
        with open(save_path, "w") as fp:
            json.dump(self.item.to_dict(), fp, indent=4)
