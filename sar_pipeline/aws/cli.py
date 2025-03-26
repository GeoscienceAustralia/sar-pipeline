import click
import logging
import os
from pathlib import Path
import shutil
from shapely.geometry import Polygon
import json

from sar_pipeline.aws.preparation.scenes import download_slc_from_asf
from sar_pipeline.aws.preparation.orbits import download_orbits_from_s3
from sar_pipeline.aws.preparation.config import RTCConfigManager
from sar_pipeline.aws.metadata.stac import BurstH5toStacManager

from sar_pipeline.dem.dem import get_cop30_dem_for_bounds
from sar_pipeline.utils.s3upload import push_files_in_folder_to_s3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class IntOrEmpty(click.ParamType):
    """Custom Click type that accepts an integer, None, or an empty string."""
    name = "int_or_empty"

    def convert(self, value, param, ctx):
        if value == "" or value is None:
            return None  # Treat empty input as None
        try:
            return int(value)
        except ValueError:
            self.fail(f"{value} is not a valid integer or empty string", param, ctx)


@click.command()
@click.option(
    "--scene",
    type=str,
    required=True,
    help="scene id. E.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD",
)
@click.option(
    "--resolution",
    required=True,
    type=int,
    help="The desired resolution of the final product",
)
@click.option(
    "--output-crs",
    required=True,
    default="",
    help="The output CRS as in integer. e.g. 3031. If None the default UTM zone for scene/burst center is used",
)
@click.option("--dem", required=True, type=click.Choice(["cop_glo30"]))
@click.option(
    "--download-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder where downloaded files should go",
)
@click.option(
    "--scratch-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder where scratch files go",
)
@click.option(
    "--out-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder where final products will be written",
)
@click.option(
    "--run-config-save-path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Path to where the RTC/opera config wil be saved",
)
@click.option("--make-folders", required=False, default=True, help="Create folders")
def get_data_for_scene_and_make_run_config(
    scene,
    resolution,
    output_crs,
    dem,
    download_folder,
    scratch_folder,
    out_folder,
    run_config_save_path,
    make_folders: bool,
):
    """Download the required data for the RTC/opera and create a configuration
    file for the run that points to appropriate files and has the required settings
    """
    logger.info(f"Downloading data for scene : {scene}")

    # make the base .yaml for RTC processing
    RTC_RUN_CONFIG = RTCConfigManager(base_config='S1_RTC.yaml')

    if make_folders:
        logger.info(f"Making output folders if not existing")
        download_folder.mkdir(parents=True, exist_ok=True)
        out_folder.mkdir(parents=True, exist_ok=True)
        scratch_folder.mkdir(parents=True, exist_ok=True)
        run_config_save_path.parent.mkdir(parents=True, exist_ok=True)

    # download the SLC and get scene metadata from asf
    logger.info(f"Downloading SLC for scene : {scene}")
    scene_folder = download_folder / "scenes"
    SCENE_PATH, asf_scene_metadata = download_slc_from_asf(scene, scene_folder)

    # # download the orbits
    logger.info(f"Downloading Orbits for scene : {scene}")
    orbit_folder = download_folder / "orbits"
    ORBITS_PATH = download_orbits_from_s3(scene, orbit_folder)

    # # download the dem
    dem_folder = download_folder / "dem"
    DEM_PATH = dem_folder / f"{scene}_dem.tif"
    scene_polygon = Polygon(asf_scene_metadata.geometry["coordinates"][0])
    bounds = scene_polygon.bounds

    logger.info(f"Downloading DEM type `{dem}` to path : {DEM_PATH}")
    get_cop30_dem_for_bounds(
        bounds=bounds,
        save_path=DEM_PATH,
        ellipsoid_heights=True,
        adjust_at_high_lat=True,
        buffer_pixels=None,
        buffer_degrees=0.3,
        cop30_folder_path=dem_folder,
        geoid_tif_path=dem_folder / f"{scene}_geoid.tif",
        download_dem_tiles=True,
        download_geoid=True,
    )

    # Update input and ancillery data
    logger.info(
        f"Updating the run config for scene"
    )
    gk = "runconfig.groups"
    RTC_RUN_CONFIG.set(f"{gk}.input_file_group.safe_file_path", [str(SCENE_PATH)])
    RTC_RUN_CONFIG.set(
        f"{gk}.input_file_group.source_data_access",
        asf_scene_metadata.properties["url"],
    )
    RTC_RUN_CONFIG.set(f"{gk}.input_file_group.orbit_file_path", [str(ORBITS_PATH)])
    RTC_RUN_CONFIG.set(f"{gk}.dynamic_ancillary_file_group.dem_file", str(DEM_PATH))
    RTC_RUN_CONFIG.set(f"{gk}.dynamic_ancillary_file_group.dem_file_description", "tmp")

    # Update Outputs
    RTC_RUN_CONFIG.set(f"{gk}.product_group.output_dir", str(out_folder))
    RTC_RUN_CONFIG.set(f"{gk}.product_group.scratch_path", str(scratch_folder))

    # set the polarisation
    POLARIZATION = asf_scene_metadata.properties["polarization"]
    POLARIZATION_TYPE = (
        "dual-pol" if len(POLARIZATION) > 2 else "co-pol"
    )  # string for template value
    RTC_RUN_CONFIG.set(f"{gk}.processing.polarization", POLARIZATION_TYPE)
    
    # update the burst resolution
    bk = "runconfig.groups.processing.geocoding.bursts_geogrid"
    RTC_RUN_CONFIG.set(f"{bk}.x_posting", int(resolution))
    RTC_RUN_CONFIG.set(f"{bk}.y_posting", int(resolution))
    RTC_RUN_CONFIG.set(f"{bk}.x_snap", int(resolution))
    RTC_RUN_CONFIG.set(f"{bk}.y_snap", int(resolution))

    # update the burst crs if it has been set
    if output_crs and output_crs is not None:
        RTC_RUN_CONFIG.set(f"{bk}.output_epsg", int(output_crs))
    
    # save the config
    logger.info(f"Saving config to : {run_config_save_path}")
    RTC_RUN_CONFIG.save(run_config_save_path)


@click.command()
@click.option(
    "--results-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder containing the burst outputs from RTC/opera",
)
@click.option(
    "--run-config-path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Path to the config path used to run RTC opera",
)
@click.option(
    "--collection",
    required=True,
    type=str,
    help="The collection the products belong to. e.g. s1_rtc_c1",
)
@click.option(
    "--s3-bucket", required=True, type=str, help="The bucket to upload the files"
)
@click.option(
    "--s3-project-folder",
    required=True,
    type=str,
    help="The folder within the bucket to upload the files. Note the "
    "final path follows the patter in the description of this function.",
)
def make_rtc_opera_stac_and_upload_bursts(
    results_folder: Path,
    run_config_path: Path,
    collection: str,
    s3_bucket: str,
    s3_project_folder: str,
):
    """makes STAC metadata for opera-rtc and uploads them to a desired s3 bucket.
    The final path in s3 will follow the following pattern:
    s3_bucket/s3_folder/collection/burst_year/burst_month/burst_day/burst_id/*files
    """

    # iterate through the burst directory and create STAC metadata
    burst_folders = [x for x in results_folder.iterdir() if x.is_dir()]
    for i, burst_folder in enumerate(burst_folders):
        logger.info(
            f"Making STAC metadata for burst {i+1} of {len(burst_folders)} : {burst_folder}"
        )
        # copy the run config file to the burst folder
        shutil.copy(run_config_path, burst_folder / run_config_path.name)
        # load in the .h5 file containing metadata for each burst
        burst_h5_files = list(burst_folder.glob("*.h5"))
        assert (
            len(burst_h5_files) == 1
        ), f"{len(burst_h5_files)} .h5 files found. Expecting 1 for in {burst_folder}"
        burst_h5_filepath = burst_folder / burst_h5_files[0]
        # make the stac metadata from the .h5 metadata
        logging.info(f"Making stac metadata from .h5 file")
        # initialise the class to convert data from the .h5 to a stac doc
        burst_stac_manager = BurstH5toStacManager(
            h5_filepath=burst_h5_filepath,
            collection=collection,
            s3_bucket=s3_bucket,
            s3_project_folder=s3_project_folder,
        )
        # make the stac item based
        burst_stac_manager.make_stac_item_from_h5()
        # add properties to the stac foc
        burst_stac_manager.add_properties_from_h5()
        # add the assets to the stac doc
        burst_stac_manager.add_assets_from_folder(burst_folder)
        # add the links to the stac doc
        burst_stac_manager.add_links_from_h5()
        # add additional links
        stac_filename = "metadata.json"
        burst_stac_manager.add_self_link(filename=stac_filename)
        # save the metadata
        burst_stac_manager.save(burst_folder / stac_filename)
        # TODO validate the stac item when finalised
        # burst_stac_manager.item.validate()
        # push folder to S3
        push_files_in_folder_to_s3(
            burst_folder, s3_bucket, burst_stac_manager.burst_s3_subfolder
        )
