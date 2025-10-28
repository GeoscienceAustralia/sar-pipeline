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


class NCIMissingSceneError(Exception):
    """Exception raised when scenes cannot be found on NCI"""

    pass


def find_scene_file_from_api(
    scene: str,
    pygssearch_env_executable: Optional[Union[str, Path]] = None,
    pygssearch_env_name: Optional[Union[str, Path]] = None,
    service: str = "https://catalogue.copernicus.gov.au/odata/v1",
) -> Path:

    # Hard code the path on NCI
    SCENE_DIR = Path("/g/data/fj7/DEAnt/Sentinel-1")

    _, metadata = query_scene_from_aus_cop_hub(
        scene,
        pygssearch_env_executable,
        pygssearch_env_name,
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

    # Hard code the path on NCI
    SCENE_DIR = Path("/g/data/fj7/Copernicus/Sentinel-1/C-SAR/")

    scene_product = get_product_type_from_scene_id(scene_id)

    # Parse the scene dates -- only start date is needed for search
    scene_start, _ = get_dates_from_scene_id(scene_id)

    # Extract year and month of first path to provide for file search
    year = scene_start.strftime("%Y")
    month = scene_start.strftime("%m")

    # Set path on GADI and search
    search_path = SCENE_DIR.joinpath(f"{scene_product}/{year}/{year}-{month}/")
    file_path = list(search_path.rglob(f"{scene_id}.zip"))

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


def find_scene_file(scene: str):

    try:
        logger.info("Searching Australian Copernicus Hub API for scene.")
        scene_path = find_scene_file_from_api(scene)
    except FileNotFoundError as api_error:
        logger.warning("Unable to identify path to scene from API.")

        try:
            logger.info("Searching NCI filesystem for scene.")
            scene_path = find_scene_file_from_id(scene)
        except NonSingleSceneResultError as filesystem_error:
            logger.warning("Unable to identify path to single scene on NCI filesystem.")

            raise NCIMissingSceneError(
                "Unable to find requested scene on NCI"
            ) from filesystem_error
