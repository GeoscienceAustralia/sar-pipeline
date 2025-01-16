from datetime import datetime
from pathlib import Path
import re

SCENE_DIR = Path("/g/data/fj7/Copernicus/Sentinel-1/C-SAR/GRD/")


def parse_scene_file_sensor(scene_id: str) -> str:
    """Extract Sentinel-1 sensor string (SA1,S1B,S1C,S1D) from scene ID

    Parameters
    ----------
    scene_id : str
        Sentinel-1 scene ID
        e.g. S1A_EW_GRDM_1SDH_20220612T120348_20220612T120452_043629_053582_0F6

    Returns
    -------
    str
        Sensor string. Should be one of S1A, S1B, S1C, or S1D

    Raises
    ------
    ValueError
        Did not find any of S1A, S1B, S1C, or S1D in the scene ID
    """
    # Expect files to be prefaced with any of S1A, S1B, S1C, or S1D, followed by underscore
    pattern = r"^(S1[A|B|C|D])_"

    match = re.match(pattern, scene_id)

    if not match:
        raise ValueError(
            "No valid sensor was found in the scene ID. Valid sensors are S1A, S1B, S1C, or S1D"
        )

    return match.group(1)


def parse_scene_file_dates(scene_id: str) -> tuple[datetime, datetime]:
    """Extracts start_date and end_date from the given scene ID.

    Parameters
    ----------
    scene_id : str
        Sentinel-1 scene ID
        e.g. S1A_EW_GRDM_1SDH_20220612T120348_20220612T120452_043629_053582_0F6

    Returns
    -------
    tuple[datetime, datetime]
        A tuple containing the start and stop date for the scene as datetimes
        e.g. (datetime(2022,06,12,12,3,48), datetime(2022,06,12,12,4,52))

    Raises
    ------
    ValueError
        Did not find a match to the expected date pattern of start_date followed by end_date in the scene ID
    """
    # Regex pattern to match the dates
    pattern = r"(?P<start_date>\d{8}T\d{6})_" r"(?P<stop_date>\d{8}T\d{6})_"

    match = re.search(pattern, scene_id)

    if not match:
        raise ValueError("The input string does not match the expected format.")

    start_date = datetime.strptime(match.group("start_date"), "%Y%m%dT%H%M%S")
    stop_date = datetime.strptime(match.group("stop_date"), "%Y%m%dT%H%M%S")

    return (start_date, stop_date)


def find_scene_file_from_id(scene_id: str) -> Path:
    """Finds the path to the scene on GADI based on the scene ID

    Parameters
    ----------
    scene_id : str
        Sentinel-1 scene ID
        e.g. S1A_EW_GRDM_1SDH_20220612T120348_20220612T120452_043629_053582_0F6

    Returns
    -------
    Path
        Location of scene on NCI GADI

    Raises
    ------
    RuntimeError
        Found more than one file -- expects one
    RuntimeError
        Found no files -- expects one. Or another Error
    """

    # Parse the scene dates -- only start date is needed for search
    scene_start, _ = parse_scene_file_dates(scene_id)

    # Extract year and month of first path to provide for file search
    year = scene_start.strftime("%Y")
    month = scene_start.strftime("%m")

    # Set path on GADI and search
    search_path = SCENE_DIR.joinpath(f"{year}/{year}-{month}/")
    file_path = list(search_path.rglob(f"{scene_id}.zip"))

    # Identify file
    if len(file_path) == 1:
        scene_path = file_path[0]
    elif len(file_path) > 1:
        raise RuntimeError("More than one file found. Review before proceeding")
    else:
        raise RuntimeError(
            "No files found or some other error. Review before proceeding"
        )

    return scene_path
