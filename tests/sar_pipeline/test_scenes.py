from sar_pipeline.preparation.downloads.scenes import (
    query_scene_from_asf,
    query_scene_from_cdse,
    query_scene_from_aus_cop_hub,
)
from sar_pipeline.utils.environment_variables import identify_and_load_missing_env_vars

import logging
from dotenv import load_dotenv
import os
from pathlib import Path
import pytest

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parents[1]
TEST_DOWNLOAD_WORKSPACE = CURRENT_DIR / Path("data/TMP/downloads")

# check if the required env variables are set
REQUIRED_ENV_VARIABLES = ["PYGSSEARCH_CONDA_ENV"]
# check if the required env variables are set
identify_and_load_missing_env_vars(
    required_env_vars=REQUIRED_ENV_VARIABLES, dotenv_location=PROJECT_ROOT
)

pygssearch_conda_env = os.getenv("PYGSSEARCH_CONDA_ENV")

scene_1 = "S1A_EW_GRDM_1SDH_20200330T165825_20200330T165929_031907_03AF02_8570"
scene_2 = "S1B_EW_GRDM_1SDH_20210914T112333_20210914T112403_028693_036C96_3EA8"
scene_3 = "S1B_IW_SLC__1SSH_20211216T123605_20211216T123634_030050_03968D_9501"
scene_4 = "S1A_IW_SLC__1SDV_20240109T195221_20240109T195248_052034_0649D6_1FF6"

scenes = [scene_1, scene_2, scene_3, scene_4]
# Make a separate list for AusCopHub that only contains Antarctic scenes
aus_cop_hub_scenes = [scene_1, scene_2, scene_3]


@pytest.mark.parametrize("scene", scenes)
def test_query_scene_from_asf(scene: str):
    query_result = query_scene_from_asf(scene)
    assert len(query_result) == 1


@pytest.mark.parametrize("scene", scenes)
def test_query_scene_from_cdse(scene: str):
    query_result = query_scene_from_cdse(scene)
    assert len(query_result) == 1


@pytest.mark.parametrize("scene", aus_cop_hub_scenes)
def test_query_scene_from_aus_cop_hub(scene: str):
    _, metadata = query_scene_from_aus_cop_hub(
        scene,
        pygssearch_conda_env=pygssearch_conda_env,
    )
    assert metadata["Name"] == scene + ".zip"
