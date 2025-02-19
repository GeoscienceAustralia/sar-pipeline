from datetime import datetime
from pathlib import Path
import re

from sar_pipeline.nci.preparation.scenes import (
    parse_scene_file_dates,
)


def find_latest_orbit_for_scene(scene_id: str, orbit_files: list[Path]) -> Path:
    """Identifies the most recent orbit file available for a given scene, based
    on the scene's start and end date.

        Parameters
        ----------
        scene_id : str
            Sentinel-1 scene ID
            e.g. S1A_EW_GRDM_1SDH_20220612T120348_20220612T120452_043629_053582_0F6
        orbit_directories : list[Path]
            directories to search for the latest orbit file

        Returns
        -------
        Path
            File path to latest orbit file on NCI
    """

    scene_start, scene_stop = parse_scene_file_dates(scene_id)

    latest_orbit = find_latest_orbit_covering_window(
        orbit_files, scene_start, scene_stop
    )

    return latest_orbit


def find_orbits(directories: list[Path], extension: str = ".EOF") -> list[Path]:
    """_summary_

    Parameters
    ----------
    directories : list[Path]
        A list of directories to search for orbit files
    extension : str, optional
        The extension for orbit files, by default ".EOF"

    Returns
    -------
    list[Path]
        A list of orbit files for every directory searched
    """

    matching_files = []
    for directory in directories:
        if directory.is_dir():
            matching_files.extend(directory.glob(f"*{extension}"))
    return matching_files


def find_latest_orbit_covering_window(
    orbit_files: list[Path], window_start: datetime, window_stop: datetime
) -> Path:
    """For a list of orbit files, finds the file with the latest publish date that
    covers the time window specified by a start and stop datetime.

    Parameters
    ----------
    orbit_files : list[Path]
        A list of orbit files
    window_start : datetime
        The start of the window the orbit must cover
    window_stop : datetime
        The end of the window the orbit must cover

    Returns
    -------
    Path
        the orbit file with the latest published date that covers the window
    """

    orbits_files_in_window = filter_orbits_to_cover_time_window(
        orbit_files, window_start, window_stop
    )

    latest_orbit = filter_orbits_to_latest(orbits_files_in_window)

    return latest_orbit


def filter_orbits_to_cover_time_window(
    orbit_files: list[Path],
    window_start: datetime,
    window_stop: datetime,
) -> list[dict[str, Path | datetime]]:
    """For a list of orbit files, finds all files that cover the time window
    specified by a start and stop datetime.

    Parameters
    ----------
    orbit_files : list[Path]
        A list of orbit files
    window_start : datetime
        The start of the window the orbit must cover
    window_stop : datetime
        The end of the window the orbit must cover

    Returns
    -------
    list[dict[str, Path | datetime]]
        _description_

    Raises
    ------
    ValueError
        _description_
    """

    matching_orbits = []
    for orbit_file in orbit_files:
        orbit_published, orbit_start, orbit_stop = parse_orbit_file_dates(orbit_file)

        if window_start >= orbit_start and window_stop <= orbit_stop:
            orbit_metadata = {"orbit": orbit_file, "published_date": orbit_published}
            matching_orbits.append(orbit_metadata)

    if not matching_orbits:
        raise ValueError("No orbits were found within the specified time widow.")

    return matching_orbits


def filter_orbits_to_latest(orbits: list[dict[str, Path | datetime]]) -> Path:
    """For a list of orbit files and published dates, find the orbit file with the latest published date.

    Parameters
    ----------
    orbits : list[dict[str, Path  |  datetime]]
        List of orbits, where each orbit is a dictionary of
        {"orbit": Path, "published_date": datetime}

    Returns
    -------
    Path
        The path to the orbit file with the latest published date

    Raises
    ------
    ValueError
        _description_
    """

    latest_orbit = max(orbits, key=lambda x: x["published_date"])

    latest_orbit_file = latest_orbit["orbit"]

    return latest_orbit_file


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
