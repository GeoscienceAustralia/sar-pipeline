import click
import logging
import os
from pathlib import Path
import shutil
from shapely.geometry import Polygon
from datetime import datetime

from sar_pipeline.aws.preparation.scenes import download_slc_from_asf
from sar_pipeline.aws.preparation.orbits import download_orbits_from_s3
from sar_pipeline.aws.preparation.config import RTCConfigManager
from sar_pipeline.aws.metadata.stac import RTCStacManager
from sar_pipeline.aws.metadata.h5 import RTCH5Manager

from sar_pipeline.nci.preparation.dem import get_cop30_dem_for_bounds
from sar_pipeline.nci.upload.push_folder_to_s3 import push_files_in_folder_to_s3

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.argument("scene", type=str)
@click.argument("base_rtc_config", type=str)
@click.argument("dem", type=str)
@click.argument("download_folder", type=str)
@click.argument("scratch_folder", type=str)
@click.argument("out_folder", type=str)
@click.argument("config_path", type=str)
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
    click.echo(f'Downloading data for scene : {scene}')
    click.echo(f'Saving files to : {download_folder}')

    # make the base .yaml for RTC processing
    RTC_RUN_CONFIG = RTCConfigManager(base_rtc_config)
    
    #The following subdirectories will be made in download_folder:
    # - scenes : downloaded and unzipped SAFE file for scene
    # - orbits : orbit files for scene
    # - dem : dem for scene 
    # - scratch : scratch folder for processing

    if make_folders:
        os.makedirs(download_folder, exist_ok=True)
        os.makedirs(out_folder, exist_ok=True)
        os.makedirs(scratch_folder, exist_ok=True)
        os.makedirs(Path(config_path).parent, exist_ok=True)

    # download the SLC and get scene metadata from asf
    scene_folder = Path(download_folder) / Path('scenes')
    SCENE_PATH, asf_scene_metadata = download_slc_from_asf(scene, scene_folder)

    # # download the orbits
    orbit_folder = Path(download_folder) / Path('orbits')
    ORBITS_PATH = download_orbits_from_s3(scene, orbit_folder)

    # # download the dem
    dem_folder = Path(download_folder) / Path('dem')
    DEM_PATH = dem_folder / f'{scene}_dem.tif'
    scene_polygon = Polygon(asf_scene_metadata.geometry['coordinates'][0])
    bounds = scene_polygon.bounds
    # bounds = (163.126465, -78.615303, 172.387283, -76.398262)
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
    gk = 'runconfig.groups'
    RTC_RUN_CONFIG.set(f'{gk}.input_file_group.safe_file_path',[str(SCENE_PATH)])
    RTC_RUN_CONFIG.set(f'{gk}.input_file_group.orbit_file_path',[str(ORBITS_PATH)])
    RTC_RUN_CONFIG.set(f'{gk}.dynamic_ancillary_file_group.dem_file',str(DEM_PATH))
    RTC_RUN_CONFIG.set(f'{gk}.dynamic_ancillary_file_group.dem_file_description','tmp')
    #RTC_RUN_CONFIG.set(f'{gk}.static_ancillary_file_group.burst_database_file','')

    # Update Outputs
    RTC_RUN_CONFIG.set(f'{gk}.product_group.output_dir',str(out_folder))
    RTC_RUN_CONFIG.set(f'{gk}.product_group.scratch_path',str(scratch_folder))

    # set the polarisation
    POLARIZATION = asf_scene_metadata.properties['polarization']
    POLARIZATION_TYPE = 'dual-pol' if len(POLARIZATION) > 2 else 'co-pol' # string for template value
    RTC_RUN_CONFIG.set(f'{gk}.processing.polarization',POLARIZATION_TYPE)

    # save the config
    click.echo(f'Saving config to : {config_path}')
    RTC_RUN_CONFIG.save(config_path)


@click.command()
@click.argument("results_folder", type=str)
@click.argument("run_config_path", type=str)
@click.argument("s3_bucket", type=str)
@click.argument("s3_folder", type=str)
def make_rtc_opera_stac_and_upload_bursts(results_folder, run_config_path, s3_bucket, s3_folder):
    """make STAC metadata for opera-rtc. Point at results folder
    containing the bursts"""

    results_folder = Path(results_folder)
    run_config_path = Path(run_config_path)

    # iterate through the burst directory and create STAC metadata
    burst_folders = [x for x in results_folder.iterdir() if x.is_dir()]
    for i,burst_folder in enumerate(burst_folders):
        logger.info(f'Making STAC metadata for burst {i+1} of {len(burst_folders)} : {burst_folder}')
        # copy the run config file to the burst folder
        shutil.copy(run_config_path, burst_folder / run_config_path.name)
        # load in the base stac for each burst
        burst_stac = RTCStacManager()
        # load in the .h5 file containing metadata for each burst
        burst_h5 = list(burst_folder.glob('*.h5'))
        assert len(burst_h5) == 1, f'{len(burst_h5)} .h5 files found. Expecting 1 for in {burst_folder}'
        burst_h5 =  RTCH5Manager(burst_folder / burst_h5[0])
        start_dt = burst_h5.get_value('metadata/sourceData/zeroDopplerStartTime')
        start_dt = start_dt.decode("utf-8")
        start_dt = datetime.fromisoformat(start_dt.rstrip("Z")) # Convert to datetime
        s3_burst_folder = Path(s3_folder) / f'{start_dt.year}/{start_dt.month}/{start_dt.day}/{burst_folder.name}' 
        # update the metadata for a given burst
        ...
        # save thge stac metadata to the burst folder 
        burst_stac.save(burst_folder / 'metadata.json')
        # push folder to S3
        push_files_in_folder_to_s3(burst_folder, s3_bucket, s3_burst_folder)