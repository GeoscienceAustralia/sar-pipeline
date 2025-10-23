from sar_pipeline.preparation.downloads.scenes import (
    query_scene_from_asf,
    query_scene_from_cdse,
    query_scene_from_aus_cop_hub,
)

import logging
from dotenv import load_dotenv
import os
from pathlib import Path
import pytest

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parents[1]
TEST_DOWNLOAD_WORKSPACE = CURRENT_DIR / Path("data/TMP/downloads")

REQUIRED_ENV_VARIABLES = [
    "PYGSSEARCH_ENV_EXECUTABLE",
    "PYGSSEARCH_ENV_NAME",
]
# check if the required env variables are set
missing = [var for var in REQUIRED_ENV_VARIABLES if not os.getenv(var)]

if missing:
    logger.warning(f"Missing required environment variables: {', '.join(missing)}")
    logger.info(
        f"The following environment variables must be set for test: {REQUIRED_ENV_VARIABLES}"
    )

    # test may be run locally which requires a secret file to set the variables
    logger.info(
        f"Attempting to load from .env file from the project root : {PROJECT_ROOT / ".env"}"
    )

    try:
        # load the environment secrets from a local file
        # see docs/workflows/aws.md for required variables
        # store in project root in .env file
        load_dotenv(PROJECT_ROOT / ".env")
        missing = [var for var in REQUIRED_ENV_VARIABLES if not os.getenv(var)]
        if missing:
            raise ValueError(
                f".env was found but some variables are missing. The following environment variables must be set for test: {REQUIRED_ENV_VARIABLES}"
            )

    except:
        raise FileExistsError(
            "Could not find .env file at project root containing required environment variables for run. "
            "Create this file with required variables OR ensure environment is configured correctly "
            "(e.g. when running automated tests on GitHub)"
        )


pygssearch_env_executable = os.getenv("PYGSSEARCH_ENV_EXECUTABLE")
pygssearch_env_name = os.getenv("PYGSSEARCH_ENV_NAME")

scene_1 = "S1A_EW_GRDM_1SDH_20200330T165825_20200330T165929_031907_03AF02_8570"
scene_2 = "S1B_EW_GRDM_1SDH_20210914T112333_20210914T112403_028693_036C96_3EA8"
scene_3 = "S1B_IW_SLC__1SSH_20211216T123605_20211216T123634_030050_03968D_9501"
scene_4 = "S1A_IW_SLC__1SDV_20240109T195221_20240109T195248_052034_0649D6_1FF6"

scenes = [scene_1, scene_2, scene_3, scene_4]


@pytest.mark.parametrize("scene", scenes)
def test_query_scene_from_asf(scene: str):
    query_result = query_scene_from_asf(scene)
    assert len(query_result) == 1


@pytest.mark.parametrize("scene", scenes)
def test_query_scene_from_cdse(scene: str):
    query_result = query_scene_from_cdse(scene)
    assert len(query_result) == 1


@pytest.mark.parametrize("scene", scenes)
def test_query_scene_from_aus_cop_hub(scene: str):
    if pygssearch_env_executable and pygssearch_env_name:
        _, metadata = query_scene_from_aus_cop_hub(
            scene,
            pygssearch_env_executable=pygssearch_env_executable,
            pygssearch_env_name=pygssearch_env_name,
        )
        assert metadata["Name"] == scene + ".zip"
