import click
import logging
import os
from pathlib import Path
from shapely.geometry import Polygon

from sar_pipeline.aws.preparation.scenes import download_slc_from_asf
from sar_pipeline.aws.preparation.orbits import download_orbits_from_s3
from sar_pipeline.aws.preparation.dem import download_dem
from sar_pipeline.aws.preparation.config import RTCConfigManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.argument("scene", type=str)
@click.argument("base_rtc_config", type=str)
@click.argument("download_folder", type=str)
@click.argument("out_folder", type=str)
@click.argument("config_path", type=str)
def get_data_for_scene_and_make_run_config(
        scene : str, 
        base_rtc_config : str,
        download_folder : Path,
        out_folder : Path,
        config_path : Path,
        make_folders : bool = True,
    ):
    click.echo(f'Getting data for scene : {scene}')
    click.echo(f'Saving files to : {download_folder}')
    click.echo(f'Setting the product folder to : {out_folder}')
    
    #The following subdirectories will be made in download_folder:
    # - scenes : downloaded and unzipped SAFE file for scene
    # - orbits : orbit files for scene
    # - dem : dem for scene 
    # - scratch : scratch folder for processing

    # make the download folder if doesnt exist
    if make_folders:
        os.makedirs(download_folder, exist_ok=True)

    # # download the SLC and get scene metadata from asf
    scene_folder = Path(download_folder) / Path('scenes')
    SCENE_PATH, asf_scene_metadata = download_slc_from_asf(scene, scene_folder)

    # # download the orbits
    orbit_folder = Path(download_folder) / Path('orbits')
    ORBITS_PATH = download_orbits_from_s3(scene, orbit_folder)

    # # download the dem
    dem_folder = Path(download_folder) / Path('dem')
    scene_polygon = Polygon(asf_scene_metadata.geometry['coordinates'][0])
    bounds = scene_polygon.bounds
    #bounds = (163.126465, -78.615303, 172.387283, -76.398262)
    DEM_PATH = download_dem(bounds=bounds, download_folder=dem_folder)

    # make the base .yaml for RTC processing
    RTC_RUN_CONFIG = RTCConfigManager(base_rtc_config)

    # update the values based on the information provided
    # save the config
    RTC_RUN_CONFIG.save(config_path)





