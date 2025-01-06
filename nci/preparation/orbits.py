from datetime import datetime
from pathlib import Path
import re

# Constants for NCI
S1_DIR = Path("/g/data/fj7/Copernicus/Sentinel-1/")
POE_DIR = "POEORB"
RES_DIR = "RESORB"
ORBIT_DIRS = [POE_DIR, RES_DIR]
SENSORS = ["S1A", "S1B"]

def parse_scene_file_dates(scene_id: str) -> tuple[datetime, datetime]:
    """
    Extracts start_date and end_date from the given scene ID.
    """
    # Regex pattern to match the dates
    pattern = (r"(?P<start_date>\d{8}T\d{6})_"
               r"(?P<stop_date>\d{8}T\d{6})_")
    
    match = re.search(pattern, scene_id)

    if not match:
        raise ValueError("The input string does not match the expected format.")
    
    start_date = datetime.strptime(match.group('start_date'), "%Y%m%dT%H%M%S")
    stop_date = datetime.strptime(match.group('stop_date'), "%Y%m%dT%H%M%S")

    return (start_date, stop_date)


def parse_orbit_file_dates(orbit_file_name: str) -> tuple[datetime, datetime, datetime]:
    """
    Extracts published_date, start_date, and end_date from the given orbit file.
    Filename example: S1A_OPER_AUX_POEORB_OPOD_20141207T123431_V20141115T225944_20141117T005944.EOF
    - Published: 20141207T123431
    - Start: 20141115T225944
    - End: 20141117T005944

    Args:
        file_name (str): The orbit file name as a string.

    Returns:
        tuple(datetime): a tuple of datetimes for published, start and end of the orbit file
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

def find_latest_orbit_for_scene(scene_id: str, poe_only: bool = True):
    """
    Identifies the most recent orbit file available for a given scene, based 
    on the scene's start and end date.
    """

    scene_start, scene_stop = parse_scene_file_dates(scene_id)

    relevant_orbits = []

    for orbit_dir in ORBIT_DIRS:
        orbit_dir_path = S1_DIR / orbit_dir
        for sensor in SENSORS:
            orbit_files_path = orbit_dir_path / sensor
            orbit_files = orbit_files_path.glob("*.EOF")

            for orbit_file in orbit_files:

                orbit_published, orbit_start, orbit_stop = parse_orbit_file_dates(orbit_file)
                
                # Check if scene falls within orbit 
                if scene_start >= orbit_start and scene_stop <= orbit_stop:
                    orbit_metadata = (orbit_file, orbit_dir, orbit_published)
                    relevant_orbits.append(orbit_metadata)

    if poe_only:
        relevant_orbits = [item for item in relevant_orbits if item[1] == POE_DIR]
    
    # If relevant_orbits is empty, set latest_orbit to None
    latest_orbit = max(relevant_orbits, key=lambda x: x[2]) if relevant_orbits else None

    if latest_orbit is None:
        raise ValueError("No valid orbit was found.")
    
    return latest_orbit

