from datetime import datetime
from pathlib import Path
import re

SCENE_DIR = Path("/g/data/fj7/Copernicus/Sentinel-1/C-SAR/GRD/")

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

def find_scene_file_from_id(scene_id: str) -> Path:
    """
    Finds the path to the scene on GADI based on the scene ID
    """

    # Parse the scene dates -- only start date is needed for search
    scene_start, _ = parse_scene_file_dates(scene_id) 

    # Extract year and month of first path to provide for file search
    year = scene_start.strftime('%Y')
    month = scene_start.strftime('%m')

    # Set path on GADI and search
    search_path = SCENE_DIR.joinpath(f"{year}/{year}-{month}/")
    file_path = list(search_path.rglob(f"{scene_id}.zip"))

    # Identify file
    if len(file_path) == 1:
        scene_path = file_path[0]
    elif len(file_path) > 1:
        raise RuntimeError("More than one file found. Review before proceeding")
    else:
        raise RuntimeError("No files found or some other error. Review before proceeding")
    
    return scene_path