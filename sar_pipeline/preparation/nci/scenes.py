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
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_SCENE_DATA_SOURCES = ["API", "FILESYSTEM"]


class NCIMissingSceneError(Exception):
    """Exception raised when scenes cannot be found on NCI"""

    pass


def find_scene_file_from_api(
    scene: str,
    pygssearch_conda_env: Optional[Union[str, Path]] = None,
    service: str = "https://catalogue.copernicus.gov.au/odata/v1",
) -> Path:

    logger.info("Searching Australian Copernicus Hub API for scene.")

    # Hard code the path on NCI
    SCENE_DIR = Path("/g/data/fj7/DEAnt/Sentinel-1")

    _, metadata = query_scene_from_aus_cop_hub(
        scene,
        pygssearch_conda_env,
        service,
    )

    scene_uuid = metadata["Id"]
    scene_path = (
        SCENE_DIR / scene_uuid[0:2] / scene_uuid[2:4] / scene_uuid / f"{scene}.zip"
    )

    if not scene_path.is_file():
        raise FileNotFoundError(
            f"Unable to locate scene through API based on retrieved UUID {scene_uuid}. Expected path is {scene_path}"
        )

    return scene_path


def find_scene_file_from_filesystem(scene: str) -> Path:
    """Finds the path to the scene in the older AusCopHub filesystem based on the scene ID

    Parameters
    ----------
    scene : str
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

    logger.info("Searching NCI filesystem for scene.")

    # Hard code the path on NCI
    SCENE_DIR = Path("/g/data/fj7/Copernicus/Sentinel-1/C-SAR/")

    scene_product = get_product_type_from_scene_id(scene)

    # Parse the scene dates -- only start date is needed for search
    scene_start, _ = get_dates_from_scene_id(scene)

    # Extract year and month of first path to provide for file search
    year = scene_start.strftime("%Y")
    month = scene_start.strftime("%m")

    # Set path on GADI and search
    search_path = SCENE_DIR.joinpath(f"{scene_product}/{year}/{year}-{month}/")
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
