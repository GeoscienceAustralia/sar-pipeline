import logging
import os
from pathlib import Path
from typing import Union, Optional

from sar_pipeline.utils.sentinel1 import (
    get_product_type_from_scene_id,
    get_dates_from_scene_id,
)

from sar_pipeline.preparation.downloads.scenes import (
    query_scene_from_aus_cop_hub,
    NonSingleSceneResultError,
    MissingEnvironmentError,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_SCENE_DATA_SOURCES = ["API", "FILESYSTEM"]


class NCIMissingSceneError(Exception):
    """Exception raised when scenes cannot be found on NCI"""

    pass


class NCIMissingFilePathVariableError(Exception):
    """Exception raised when a required filepath on NCI has not been provided"""


def find_scene_file_from_api(
    scene: str,
    pygssearch_conda_env: Optional[Union[str, Path]] = None,
    api_scene_directory: Optional[Union[str, Path]] = None,
    service: str = "https://catalogue.copernicus.gov.au/odata/v1",
) -> Path:
    """Finds the path to the scene on the NCI using the pygssearch API for AusCopHub based on the scene ID

    Parameters
    ----------
    scene : str
        Sentinel-1 scene ID
        e.g. S1A_EW_GRDM_1SDH_20220612T120348_20220612T120452_043629_053582_0F6
    pygssearch_conda_env : Optional[Union[str, Path]], optional
        Path to the conda environment containing an installation of pygssearch that
        will be called in a subprocess. If not specified, the env variable
        PYGSSEARCH_CONDA_ENV will be used. By default None
    api_scene_directory : Optional[Union[str, Path]], optional
        Directory on NCI that contains scene files for the pygssearch AusCopHub API.
        If not specified, the env variable NCI_API_FILES will be used.
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
        Neither of api_scene_directory and NCI_API_FILES environment variable were set
    NCIMissingSceneError
        No valid filepath was found for the scene

    """

    logger.info("Searching Australian Copernicus Hub API for scene.")

    # Get pygssearch conda environment path if not passed to function
    pygssearch_conda_env = pygssearch_conda_env or os.getenv("PYGSSEARCH_CONDA_ENV")
    if not pygssearch_conda_env:
        raise MissingEnvironmentError(
            "Path to conda environment for pygssearch is missing. "
            "Please provide the pygssearch_conda_env argument "
            "or set the PYGSSEARCH_CONDA_ENV environment variable."
        )

    # Get directory on NCI that hosts the file system for the Aus Cop Hub API
    api_scene_directory = api_scene_directory or os.getenv("NCI_API_FILE_LOCATION")
    if not api_scene_directory:
        raise NCIMissingFilePathVariableError(
            "Path to Aus Cop Hub API filesystem on NCI is missing. "
            "Please provide the api_scene_directory argument "
            "Or set the NCI_API_FILE_LOCATION environment variable."
        )

    # Get metadata by querying the scene ID using the API
    _, metadata = query_scene_from_aus_cop_hub(
        scene,
        pygssearch_conda_env,
        service,
    )

    # Extract the scene UUID from the metadata, which informs the file path
    scene_uuid = metadata["Id"]

    # Convert api_scene_directory to path, then append location of scene as dictated by API
    api_scene_directory = Path(api_scene_directory)
    scene_path = (
        api_scene_directory
        / scene_uuid[0:2]
        / scene_uuid[2:4]
        / scene_uuid
        / f"{scene}.zip"
    )

    # Raise an error if the file does not exist
    if not scene_path.is_file():
        raise NCIMissingSceneError(
            f"Unable to locate scene through API based on retrieved UUID {scene_uuid}. Expected path is {scene_path}."
        )

    return scene_path


def find_scene_file_from_filesystem(
    scene: str,
    filesystem_scene_directory: Optional[Union[str, Path]] = None,
) -> Path:
    """Finds the path to the scene in the older AusCopHub filesystem based on the scene ID

    Parameters
    ----------
    scene : str
        Sentinel-1 scene ID
        e.g. S1A_EW_GRDM_1SDH_20220612T120348_20220612T120452_043629_053582_0F6
    filesystem_scene_directory : Optional[Union[str, Path]], optional
        Directory on NCI that contains scene files for the older AusCopHub filesystem.
        If not specified, the env variable NCI_FILESYSTEM_FILES will be used.
        By default None

    Returns
    -------
    Path
        Location of scene on NCI GADI

    Raises
    ------
    NCIMissingFilePathError
        No valid filepath was found for the scene
    NonSingleSceneResultError
        0, or more than one SLC result is found
    """

    logger.info("Searching NCI filesystem for scene.")

    # Get directory on NCI that hosts the original filesystem for Aus Cop Hub
    # This directory ceased to be updated after mid-2025
    filesystem_scene_directory = filesystem_scene_directory or os.getenv(
        "NCI_FILESYSTEM_FILE_LOCATION"
    )
    if not filesystem_scene_directory:
        raise NCIMissingFilePathVariableError(
            "Path to original Aus Cop Hub filesystem on NCI is missing. "
            "Please provide the filesystem_scene_directory argument "
            "Or set the NCI_FILESYSTEM_FILE_LOCATION environment variable."
        )

    scene_product = get_product_type_from_scene_id(scene)

    # Parse the scene dates -- only start date is needed for search
    scene_start, _ = get_dates_from_scene_id(scene)

    # Extract year and month of first path to provide for file search
    year = scene_start.strftime("%Y")
    month = scene_start.strftime("%m")

    # Set path on GADI and search
    filesystem_scene_directory = Path(filesystem_scene_directory)
    search_path = filesystem_scene_directory.joinpath(
        f"{scene_product}/{year}/{year}-{month}/"
    )
    file_path = list(search_path.rglob(f"{scene}.zip"))

    # Identify file
    if len(file_path) == 1:
        scene_path = file_path[0]
    elif len(file_path) > 1:
        raise NonSingleSceneResultError(
            "More than one file found. Review before proceeding"
        )
    else:
        raise NonSingleSceneResultError(
            "No files found or some other error. Review before proceeding"
        )

    return scene_path


def find_scene_file_from_id(
    scene: str, scene_data_source_preferences: list = ["API", "FILESYSTEM"]
):

    # Check that provided preference list is valid
    if not all(
        [
            data_source in VALID_SCENE_DATA_SOURCES
            for data_source in scene_data_source_preferences
        ]
    ):
        raise ValueError(
            f"scene_data_source_preferences valid values are {VALID_SCENE_DATA_SOURCES}"
        )

    # Define variables prior to loop -- avoids variables being unbounded
    scene_path = None
    data_source = None

    for i, data_source in enumerate(scene_data_source_preferences):
        logger.info(
            f"Attempting to find scene on NCI from preference {i+1} of {len(scene_data_source_preferences)} : {data_source}"
        )
        try:
            if data_source == "API":
                scene_path = find_scene_file_from_api(scene)
                break
            elif data_source == "FILESYSTEM":
                scene_path = find_scene_file_from_filesystem(scene)
                break
        except Exception as e:
            logger.error(
                f"Could not find scene on NCI using preference {i+1} of {len(scene_data_source_preferences)} : {data_source}",
                exc_info=True,
            )
            if data_source == scene_data_source_preferences[-1]:
                raise NCIMissingSceneError(
                    f"Unable to find requested scene on NCI from any data source provided : {scene_data_source_preferences}"
                ) from e

    logger.info(f"Scene successfully identified from: {data_source}")
    return scene_path
