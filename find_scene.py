from datetime import datetime
from dem_stitcher import stitch_dem
from pathlib import Path
from pyroSAR import identify
from utils import transform_scene_extent
from shapely.geometry import Polygon
import pandas as pd
import re
import rasterio as rio
from dataclasses import dataclass
import click

def parse_orbit_file_dates(orbit_file_name: str):
    """
    Extracts published_date, start_date, and end_date from the given orbit file.
    Filename example: /g/data/fj7/Copernicus/Sentinel-1/POEORB/S1A/S1A_OPER_AUX_POEORB_OPOD_20141207T123431_V20141115T225944_20141117T005944.EOF
    - Published: 20141207T123431
    - Start: 20141115T225944
    - End: 20141117T005944

    Args:
        file_name (Path): The input file name as a string.

    Returns:
        tuple: a tuple of datetimes for published, start and end of the orbit file
    """
    # Regex pattern to match the dates
    pattern = (r"(?P<published_date>\d{8}T\d{6})_V"
               r"(?P<start_date>\d{8}T\d{6})_"
               r"(?P<stop_date>\d{8}T\d{6})\.EOF")

    # Search for matches in the file name
    match = re.search(pattern, str(orbit_file_name))

    if not match:
        raise ValueError("The input string does not match the expected format.")

    # Extract and parse the dates into datetime objects
    published_date = datetime.strptime(match.group('published_date'), "%Y%m%dT%H%M%S")
    start_date = datetime.strptime(match.group('start_date'), "%Y%m%dT%H%M%S")
    stop_date = datetime.strptime(match.group('stop_date'), "%Y%m%dT%H%M%S")

    return (published_date, start_date, stop_date)

@click.command()
@click.argument("scene_id")
def main(scene_id: str):
    print(scene_id)
    cophub_dir = Path("/g/data/fj7/Copernicus/Sentinel-1/C-SAR/GRD/")
    script_dir = Path(__file__).parent
    config_dir = script_dir.parent.joinpath("configuration_files")
    dem_dir = script_dir.parent.joinpath("data/dem")
    print(f"Processing scene: {scene_id}")

    # Want to get start and end date to help with finding orbit file
    pattern = (r"(?P<start>\d{8}T\d{6})_"
               r"(?P<stop>\d{8}T\d{6})_")
    
    match = re.search(pattern, scene_id)
    if not match:
        raise ValueError("The input string does not match the expected format.")
    
    scene_start = datetime.strptime(match.group('start'), "%Y%m%dT%H%M%S")
    scene_stop = datetime.strptime(match.group('stop'), "%Y%m%dT%H%M%S")

    # Extract year and month of first path to provide for file search
    year = scene_start.strftime('%Y')
    month = scene_start.strftime('%m')

    # Set path on Gadi
    search_path = cophub_dir.joinpath(f"{year}/{year}-{month}/")

    file_path = list(search_path.rglob(f"{scene_id}.zip"))

    if len(file_path) == 1:
        scene_path = file_path[0]
        print(f"Found scene: {scene_path}")
        with open(config_dir.joinpath(f"{scene_id}_config.toml"), "w") as f:
            f.write(f'scene = "{scene_path}"\n')
    elif len(file_path) > 1:
        raise RuntimeError("More than one file found. Review before proceeding")
    else:
        raise RuntimeError("No files found or some other error. Review before proceeding")


    # Look for orbit file
    S1_DIR = Path("/g/data/fj7/Copernicus/Sentinel-1/")

    ORBIT_TYPES = ["POE", "RES"]
    SENSORS = ["S1A", "S1B"]

    relevant_orbits = []

    for orbit_type in ORBIT_TYPES:
        orbit_dir = S1_DIR / f"{orbit_type}ORB"
        for sensor in SENSORS:
            orbit_file_dir = orbit_dir / sensor
            orbit_files = orbit_file_dir.glob("*.EOF")

            for orbit_file in orbit_files:

                orbit_published, orbit_start, orbit_stop = parse_orbit_file_dates(orbit_file)
                
                # Check if scene falls within orbit 
                if scene_start >= orbit_start and scene_stop <= orbit_stop:
                    orbit_metadata = (orbit_file, orbit_type, orbit_published)
                    relevant_orbits.append(orbit_metadata)

    # Filter to POE only
    poe_files = [item for item in relevant_orbits if item[1] == "POE"]

    # Find the tuple with the latest datetime
    latest_poe_file = max(poe_files, key=lambda x: x[2]) if poe_files else None

    print(f"Found orbit file: {latest_poe_file[0]}")
    with open(config_dir.joinpath(f"{scene_id}_config.toml"), "a") as f:
            f.write(f'orbit = "{latest_poe_file[0]}"\n')

    # Do DEM
    print("Checking for DEM")
    # If scene exists, extract metadata
    if scene_path.exists():
        scene_id_pyrosar = identify(scene_path)

    dem_filename = scene_id + '_dem.tif'
    dem_file = dem_dir.joinpath(dem_filename)

    if dem_file.exists():
        print(f"dem file found at {dem_file}")
    else:
        # Extract scene bounds
        scene_polygon = Polygon(scene_id_pyrosar.meta["coordinates"])
        scene_bounds = scene_polygon.bounds

        # if we are at high latitudes we need to correct the bounds due to the skewed box shape
        if (scene_bounds[1] < -50) or (scene_bounds[3] < -50):
            # Southern Hemisphere
            print(f'Adjusting scene bounds due to warping at high latitude (Southern Hemisphere)')
            scene_polygon = transform_scene_extent(scene_polygon, 4326, 3031)
            scene_bounds = scene_polygon.bounds 
            #logging.info(f'Adjusted scene bounds : {scene_bounds}')
        if (scene_bounds[1] > 50) or (scene_bounds[3] > 50):
            # Northern Hemisphere
            print(f'Adjusting scene bounds due to warping at high latitude (Northern Hemisphere)')
            scene_polygon = transform_scene_extent(scene_bounds, 4326, 3995)
            scene_bounds = scene_polygon.bounds 
            #logging.info(f'Adjusted scene bounds : {scene_bounds}')

        # Buffer scene boundaries
        buffer = 0.1
        scene_bounds_buffered = scene_polygon.buffer(buffer).bounds #buffered

        dem_data, dem_meta = stitch_dem(
            scene_bounds_buffered,
            dem_name='glo_30',
            dst_ellipsoidal_height=True,
            dst_area_or_point='Point',
            merge_nodata_value=0,
            fill_to_bounds=True,
        )

        print(f'saving dem to {dem_file}')
        with rio.open(dem_file, 'w', **dem_meta) as ds:
            ds.write(dem_data, 1)
            ds.update_tags(AREA_OR_POINT='Point')
        del dem_data

        with open(config_dir.joinpath(f"{scene_id}_config.toml"), "a") as f:
            f.write(f'dem = "{dem_file}"\n')


if __name__ == "__main__":

    main()