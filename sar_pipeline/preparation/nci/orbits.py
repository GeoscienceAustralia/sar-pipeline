from datetime import datetime
from pathlib import Path
import re
from typing import TypedDict, Optional, Union
import logging
import os

from sar_pipeline.utils.sentinel1 import (
    get_dates_from_scene_id,
    extract_metadata_from_s1_id,
)
from sar_pipeline.preparation.downloads.orbits import (
    query_orbit_from_aus_cop_hub,
    OrbitNotFoundError,
    MissingEnvironmentError,
)
from sar_pipeline.pipelines.pyrosar_gamma.filesystem import get_orbits_nci

logging.basicConfig(level=logging.INFO)


class Orbit(TypedDict):
    orbit: Path
    published_date: datetime


class NCIMissingOrbitError(Exception):
    """Exception raised when orbits cannot be found on NCI"""

    pass


class NCIMissingFilePathVariableError(Exception):
    """Exception raised when a required filepath on NCI has not been provided"""


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

    scene_start, scene_stop = get_dates_from_scene_id(scene_id)

    latest_orbit = find_latest_orbit_covering_window(
        orbit_files, scene_start, scene_stop
    )

    return latest_orbit


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
) -> list[Orbit]:
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
    list[Orbit]
        List of orbit dictionaries, where each orbit is a dictionary of
        {"orbit": Path, "published_date": datetime}

    Raises
    ------
    ValueError
        No matching orbits were found
    """

    matching_orbits = []
    for orbit_file in orbit_files:
        orbit_published, orbit_start, orbit_stop = parse_orbit_file_dates(orbit_file)

        if window_start >= orbit_start and window_stop <= orbit_stop:
            orbit_metadata: Orbit = {
                "orbit": orbit_file,
                "published_date": orbit_published,
            }
            matching_orbits.append(orbit_metadata)

    if not matching_orbits:
        raise OrbitNotFoundError(
            "No orbits were found within the specified time window."
        )

    return matching_orbits


def filter_orbits_to_latest(orbits: list[Orbit]) -> Path:
    """For a list of dicts containing orbit files and published dates, find the orbit file with the latest published date.

    Parameters
    ----------
    orbits : list[Orbit]
        List of orbit dictionaries, where each orbit is a dictionary of
        {"orbit": Path, "published_date": datetime}

    Returns
    -------
    Path
        The path to the orbit file with the latest published date
    """

    latest_orbit = max(orbits, key=lambda x: x["published_date"])

    latest_orbit_file = latest_orbit["orbit"]

    return latest_orbit_file


def parse_orbit_file_dates(
    orbit_file_name: str | Path,
) -> tuple[datetime, datetime, datetime]:
    """Extracts published_date, start_date, and end_date from the given orbit file.
    Filename example: S1A_OPER_AUX_POEORB_OPOD_20141207T123431_V20141115T225944_20141117T005944.EOF
    - Published: 20141207T123431
    - Start: 20141115T225944
    - End: 20141117T005944

    Parameters
    ----------
    orbit_file_name : str | Path
        The orbit file name as a string or a pathlib.Path

    Returns
    -------
    tuple[datetime, datetime, datetime]
        a tuple of datetimes for published, start and end of the orbit file

    Raises
    ------
    ValueError
        Did not find a match to the expected date pattern of published_date followed by start_date and end_date
    """
    if isinstance(orbit_file_name, Path):
        orbit_file_name = str(orbit_file_name)

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


def find_orbit_file_from_api(
    scene: str,
    orbit_file_types: list = ["AUX_POEORB", "AUX_RESORB"],
    pygssearch_conda_env: Optional[Union[str, Path]] = None,
    api_orbit_directory: Optional[Union[str, Path]] = None,
    service: str = "https://catalogue.copernicus.gov.au/odata/v1",
) -> Path:
    """Finds the path to the orbit on the NCI using the pygssearch API for
    AusCopHub based on the scene ID

    Parameters
    ----------
    scene : str
        Sentinel-1 scene ID
        e.g. S1A_EW_GRDM_1SDH_20220612T120348_20220612T120452_043629_053582_0F6
    pygssearch_conda_env : Optional[Union[str, Path]], optional
        Path to the conda environment containing an installation of pygssearch that
        will be called in a subprocess. If not specified, the env variable
        PYGSSEARCH_CONDA_ENV will be used. By default None
    api_orbit_directory : Optional[Union[str, Path]], optional
        Directory on NCI that contains scene files for the pygssearch AusCopHub API.
        If not specified, the env variable NCI_API_ORBIT_FILE_LOCATION will be used.
        By default None
    service : _type_, optional
        Service to query, by default "https://catalogue.copernicus.gov.au/odata/v1"

    Returns
    -------
    Path
        Location of scene on NCI GADI

    Raises
    ------
    MissingEnvironmentError
        Neither of pygssearch_conda_env and PYGSSEARCH_CONDA_ENV environment variable were set
    NCIMissingFilePathVariableError
        Neither of api_orbit_directory and NCI_API_ORBIT_FILE_LOCATION environment variable were set
    OrbitNotFoundError
        No valid orbit was found for the scene
    """

    logging.info("Searching Australian Copernicus Hub API for Orbit.")

    # Get pygssearch conda environment path if not passed to function
    pygssearch_conda_env = pygssearch_conda_env or os.getenv("PYGSSEARCH_CONDA_ENV")
    if not pygssearch_conda_env:
        raise MissingEnvironmentError(
            "Path to conda environment for pygssearch is missing. "
            "Please provide the pygssearch_conda_env argument "
            "or set the PYGSSEARCH_CONDA_ENV environment variable."
        )

    # Get directory on NCI that hosts the file system for the Aus Cop Hub API
    api_orbit_directory = api_orbit_directory or os.getenv(
        "NCI_API_ORBIT_FILE_LOCATION"
    )
    if not api_orbit_directory:
        raise NCIMissingFilePathVariableError(
            "Path to Aus Cop Hub API filesystem on NCI is missing. "
            "Please provide the api_orbit_directory argument "
            "Or set the NCI_API_ORBIT_FILE_LOCATION environment variable."
        )

    # Get metadata by querying the scene ID using the API
    metadata = query_orbit_from_aus_cop_hub(
        scene,
        pygssearch_conda_env=pygssearch_conda_env,
        orbit_file_types=orbit_file_types,
        service=service,
    )

    if not metadata:
        raise OrbitNotFoundError(
            "Orbit file cound not be found for scene via Aus Cop Hub pygssearch"
        )

    # Extract the scene UUID from the metadata, which informs the file path
    orbit_uuid = metadata["Id"]
    orbit_filename = metadata["Name"]

    # Convert api_orbit_directory to path, then append location of orbit file as dictated by API
    api_orbit_directory = Path(api_orbit_directory)
    orbit_file_path = (
        api_orbit_directory
        / orbit_uuid[0:2]
        / orbit_uuid[2:4]
        / orbit_uuid
        / orbit_filename
    )

    # Raise an error if the file does not exist
    if not orbit_file_path.is_file():
        raise NCIMissingOrbitError(
            f"Unable to locate orbit file through API based on retrieved UUID {orbit_uuid}. Expected path is {orbit_file_path}."
        )

    return orbit_file_path


def find_orbit_from_id(
    scene_id: str,
    orbit_type: str = "POE",
    nci_orbit_dir=Path("/g/data/fj7/Copernicus/Sentinel-1/"),
) -> Path:
    """
    scene_id: str:
        Scene ID, e.g.
    orbit_dir : Path, optional
        Path to orbit files
        Set to default for NCI: /g/data/fj7/Copernicus/Sentinel-1/
    orbit_type : str, optional
        The orbit type to get. Any of "POE", "RES" or "either", by default "POE"
        orbit_dir : Path, optional
    """

    # Extract metadata
    scene_metadata = extract_metadata_from_s1_id(scene_id)

    # Isolate metadata for finding orbit
    scene_sensor = scene_metadata.mission
    scene_start = scene_metadata.start_datetime
    scene_stop = scene_metadata.stop_datetime

    # Find orbit files
    try:
        logging.info("Searching for orbit file in NCI filesystem")
        orbit_files = get_orbits_nci(orbit_type, scene_sensor, nci_orbit_dir)
        orbit_file = find_latest_orbit_covering_window(
            orbit_files, scene_start, scene_stop
        )
    except OrbitNotFoundError:
        logging.info("Orbit not found on NCI")
        # format orbit types for API
        if orbit_type == "either":
            orbit_file_types = ["AUX_POEORB", "AUX_RESORB"]
        else:
            orbit_file_types = [f"AUX_{orbit_type}ORB"]
        try:
            orbit_file = find_orbit_file_from_api(
                scene_id, orbit_file_types=orbit_file_types
            )
        except OrbitNotFoundError:
            raise NCIMissingOrbitError(
                f"Could not find orbit file in NCI filesystem or through pyssearch of Aus Cop Hub"
            )

    return orbit_file
