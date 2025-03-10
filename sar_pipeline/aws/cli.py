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
from sar_pipeline.aws.metadata.stac import burst_stac_metadata_from_h5

from sar_pipeline.dem.dem import get_cop30_dem_for_bounds
from sar_pipeline.utils.s3upload import push_files_in_folder_to_s3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.argument("scene", type=str)
@click.argument("base_rtc_config", type=str)
@click.argument("dem", type=str)
@click.argument("download_folder", type=click.Path(file_okay=False, path_type=Path))
@click.argument("scratch_folder", type=click.Path(file_okay=False, path_type=Path))
@click.argument("out_folder", type=click.Path(file_okay=False, path_type=Path))
@click.argument("config_path", type=click.Path(dir_okay=False, path_type=Path))
def get_data_for_scene_and_make_run_config(
        scene : str, 
        base_rtc_config : str,
        dem : str,
        download_folder : Path,
        scratch_folder : Path,
        out_folder : Path,
        config_path : Path,
        make_folders : bool = True,
    ):
    logger.info(f'Downloading data for scene : {scene}')

    # make the base .yaml for RTC processing
    RTC_RUN_CONFIG = RTCConfigManager(base_rtc_config)

    if make_folders:
        logger.info(f'Making output folders if not existing')
        os.makedirs(download_folder, exist_ok=True)
        os.makedirs(out_folder, exist_ok=True)
        os.makedirs(scratch_folder, exist_ok=True)
        os.makedirs(config_path.parent, exist_ok=True)

    # download the SLC and get scene metadata from asf
    logger.info(f'Downloading SLC for scene : {scene}')
    scene_folder = download_folder / 'scenes'
    SCENE_PATH, asf_scene_metadata = download_slc_from_asf(scene, scene_folder)

    # # download the orbits
    logger.info(f'Downloading Orbits for scene : {scene}')
    orbit_folder = download_folder / 'orbits'
    ORBITS_PATH = download_orbits_from_s3(scene, orbit_folder)

    # # download the dem
    dem_folder = download_folder / 'dem'
    DEM_PATH = dem_folder / f'{scene}_dem.tif'
    scene_polygon = Polygon(asf_scene_metadata.geometry['coordinates'][0])
    bounds = scene_polygon.bounds
    
    logger.info(f'Downloading DEM type `{dem}` to path : {DEM_PATH}')
    get_cop30_dem_for_bounds(
        bounds = bounds,
        save_path = DEM_PATH,
        ellipsoid_heights = True,
        adjust_at_high_lat= True,
        buffer_pixels = None,
        buffer_degrees = 0.3,
        cop30_folder_path = dem_folder,
        geoid_tif_path = dem_folder / f'{scene}_geoid.tif',
        download_dem_tiles = True,
        download_geoid=True,
    )
    
    # Update input and ancillery data
    logger.info(f'Updating the run config for scene. Base config type : {base_rtc_config}')
    gk = 'runconfig.groups'
    RTC_RUN_CONFIG.set(f'{gk}.input_file_group.safe_file_path',[str(SCENE_PATH)])
    RTC_RUN_CONFIG.set(f'{gk}.input_file_group.orbit_file_path',[str(ORBITS_PATH)])
    RTC_RUN_CONFIG.set(f'{gk}.dynamic_ancillary_file_group.dem_file',str(DEM_PATH))
    RTC_RUN_CONFIG.set(f'{gk}.dynamic_ancillary_file_group.dem_file_description','tmp')

    # Update Outputs
    RTC_RUN_CONFIG.set(f'{gk}.product_group.output_dir',str(out_folder))
    RTC_RUN_CONFIG.set(f'{gk}.product_group.scratch_path',str(scratch_folder))

    # set the polarisation
    POLARIZATION = asf_scene_metadata.properties['polarization']
    POLARIZATION_TYPE = 'dual-pol' if len(POLARIZATION) > 2 else 'co-pol' # string for template value
    RTC_RUN_CONFIG.set(f'{gk}.processing.polarization',POLARIZATION_TYPE)

    # save the config
    logger.info(f'Saving config to : {config_path}')
    RTC_RUN_CONFIG.save(config_path)


@click.command()
@click.argument("results_folder", type=click.Path(file_okay=False, path_type=Path))
@click.argument("run_config_path", type=click.Path(dir_okay=False, path_type=Path))
@click.argument("s3_bucket", type=str)
@click.argument("s3_folder", type=str)
def make_rtc_opera_stac_and_upload_bursts(results_folder, run_config_path, s3_bucket, s3_folder):
    """make STAC metadata for opera-rtc. Point at results folder
    containing the bursts"""

    # iterate through the burst directory and create STAC metadata
    burst_folders = [x for x in results_folder.iterdir() if x.is_dir()]

    for i,burst_folder in enumerate(burst_folders):
        logger.info(f'Making STAC metadata for burst {i+1} of {len(burst_folders)} : {burst_folder}')
        # copy the run config file to the burst folder
        shutil.copy(run_config_path, burst_folder / run_config_path.name)
        # load in the .h5 file containing metadata for each burst
        burst_h5_files = list(burst_folder.glob('*.h5'))
        assert len(burst_h5_files) == 1, f'{len(burst_h5_files)} .h5 files found. Expecting 1 for in {burst_folder}'
        burst_h5_filepath = burst_folder / burst_h5_files[0]
        # make the stac metadata from the .h5 metadata
        logging.info(f'Making stac metadata from .h5 file')
        burst_stac_item = burst_stac_metadata_from_h5(burst_h5_filepath)
        # make s3 destination based on burst acquisition start abd burst id
        start_dt = burst_stac_item.get_datetime()
        s3_burst_folder = Path(s3_folder) / f'{start_dt.year}/{start_dt.month}/{start_dt.day}/{burst_folder.name}' 
        # save stac metadata
        logging.info(f'writing stac metadata to : {burst_folder / "metadata.json"}')
        with open(burst_folder / 'metadata.json', 'w') as fp:
            json.dump(burst_stac_item.to_dict(), fp)
        # push folder to S3
        push_files_in_folder_to_s3(burst_folder, s3_bucket, s3_burst_folder)