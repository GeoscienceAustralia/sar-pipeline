from datetime import datetime
from pathlib import Path
import re
from typing import Optional

from sar_antarctica.nci.preparation.scenes import (
    parse_scene_file_dates,
    parse_scene_file_sensor,
)

# Constants for NCI
S1_DIR = Path("/g/data/fj7/Copernicus/Sentinel-1/")
POE_DIR = "POEORB"
RES_DIR = "RESORB"


def parse_orbit_file_dates(orbit_file_name: str) -> tuple[datetime, datetime, datetime]:
    """Extracts published_date, start_date, and end_date from the given orbit file.
    Filename example: S1A_OPER_AUX_POEORB_OPOD_20141207T123431_V20141115T225944_20141117T005944.EOF
    - Published: 20141207T123431
    - Start: 20141115T225944
    - End: 20141117T005944

    Parameters
    ----------
    orbit_file_name : str
        The orbit file name as a string.

    Returns
    -------
    tuple[datetime, datetime, datetime]
        a tuple of datetimes for published, start and end of the orbit file

    Raises
    ------
    ValueError
        Did not find a match to the expected date pattern of published_date followed by start_date and end_date
    """
    # Regex pattern to match the dates
    pattern = (
        r"(?P<published_date>\d{8}T\d{6})_V"
        r"(?P<start_date>\d{8}T\d{6})_"
        r"(?P<stop_date>\d{8}T\d{6})\.EOF"
    )

    # Search for matches in the file name
    match = re.search(pattern, str(orbit_file_name))

    if not match:
        raise ValueError("The input string does not match the expected format.")

    # Extract and parse the dates into datetime objects
    published_date = datetime.strptime(match.group("published_date"), "%Y%m%dT%H%M%S")
    start_date = datetime.strptime(match.group("start_date"), "%Y%m%dT%H%M%S")
    stop_date = datetime.strptime(match.group("stop_date"), "%Y%m%dT%H%M%S")

    return (published_date, start_date, stop_date)


def find_latest_orbit_for_scene(
    scene_id: str, orbit_type: Optional[str] = None
) -> Path:
    """Identifies the most recent orbit file available for a given scene, based
    on the scene's start and end date.

    Parameters
    ----------
    scene_id : str
        Sentinel-1 scene ID
        e.g. S1A_EW_GRDM_1SDH_20220612T120348_20220612T120452_043629_053582_0F6
    orbit_type : Optional[str], optional
        Any of "POE" for POE orbits, "RES" for RES orbits, or None, by default None

    Returns
    -------
    Path
        Full file path to latest orbit file on NCI

    Raises
    ------
    ValueError
        orbit_type must be one of "POE", "RES" or None
    ValueError
        No valid orbit file was found
    """

    scene_start, scene_stop = parse_scene_file_dates(scene_id)
    scene_sensor = parse_scene_file_sensor(scene_id)

    relevant_orbits = []

    if orbit_type == "POE":
        orbit_directories = [POE_DIR]
    elif orbit_type == "RES":
        orbit_directories = [RES_DIR]
    elif orbit_type is None:
        orbit_directories = [RES_DIR, POE_DIR]
    else:
        raise ValueError("orbit_type must be one of 'POE', 'RES', or None")

    # Find all orbits for the sensor that fall within the date range of the scene
    for orbit_dir in orbit_directories:
        orbit_dir_path = S1_DIR / orbit_dir
        orbit_files_path = orbit_dir_path / scene_sensor
        orbit_files = orbit_files_path.glob("*.EOF")

        for orbit_file in orbit_files:

            orbit_published, orbit_start, orbit_stop = parse_orbit_file_dates(
                orbit_file
            )

            # Check if scene falls within orbit
            if scene_start >= orbit_start and scene_stop <= orbit_stop:
                orbit_metadata = (orbit_file, orbit_dir, orbit_published)
                relevant_orbits.append(orbit_metadata)

    # If relevant_orbits is empty, set latest_orbit to None
    latest_orbit = max(relevant_orbits, key=lambda x: x[2]) if relevant_orbits else None

    if latest_orbit is None:
        raise ValueError("No valid orbit was found.")
    else:
        latest_orbit_file = latest_orbit[0]

    return latest_orbit_file
