"""script to test sar_pipeline downloads of scenes and orbit files"""

from pathlib import Path
from dataclasses import dataclass
import logging
from dotenv import load_dotenv
import os
import pytest
import shutil

from sar_pipeline.preparation.downloads.scenes import (
    download_scene_from_preference_list,
    SceneDownloadError,
)
from sar_pipeline.preparation.downloads.orbits import (
    download_orbits_from_preference_list,
)
from sar_pipeline.utils.environment_variables import identify_and_load_missing_env_vars

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parents[2]
TEST_DOWNLOAD_WORKSPACE = CURRENT_DIR / Path("data/TMP/downloads")

REQUIRED_ENV_VARIABLES = [
    "EARTHDATA_LOGIN",
    "EARTHDATA_PASSWORD",
    "CDSE_LOGIN",
    "CDSE_PASSWORD",
    "AUS_COP_HUB_LOGIN",
    "AUS_COP_HUB_PASSWORD",
    "AUS_COP_HUB_CLIENT_ID",
    "AUS_COP_HUB_CLIENT_SECRET",
    "PYGSSEARCH_CONDA_ENV",
]
# check if the required env variables are set
identify_and_load_missing_env_vars(
    required_env_vars=REQUIRED_ENV_VARIABLES, dotenv_location=PROJECT_ROOT
)


@dataclass
class ProductDownloadTest:
    scene: str
    scene_data_sources: list
    unzip: bool
    orbit_data_sources: list
    download_folder: Path
    passes: bool  # if test should pass
    exception_type: Exception | None  # exception thrown if not passes
    downloaded_scene_path: Path  # path to downloaded scene
    downloaded_scene_url: str  # url scene was downloaded from
    downloaded_orbits_path: Path  # path to downloaded orbit file


scene_1 = "S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD"
scene_2 = "S1D_IW_SLC__1SDV_20260420T210916_20260420T210942_002435_004001_209C"

TEST_CDSE_DOWNLOAD = ProductDownloadTest(
    scene=scene_1,
    scene_data_sources=["CDSE"],
    unzip=True,
    orbit_data_sources=["CDSE"],
    download_folder=TEST_DOWNLOAD_WORKSPACE,
    passes=True,
    exception_type=None,
    downloaded_scene_path=TEST_DOWNLOAD_WORKSPACE / f"{scene_1}.SAFE",
    downloaded_scene_url="https://download.dataspace.copernicus.eu/odata/v1/Products(e948c832-d7e4-58d1-80d7-957b7f243371)",
    downloaded_orbits_path=TEST_DOWNLOAD_WORKSPACE
    / f"S1A_OPER_AUX_POEORB_OPOD_20220121T121549_V20211231T225942_20220102T005942.EOF",
)

# WARNING ASF ORBIT CURRENTLY FAILING - https://github.com/scottstanie/sentineleof/issues/80
TEST_ASF_DOWNLOAD = ProductDownloadTest(
    scene=scene_1,
    scene_data_sources=["ASF"],
    unzip=True,
    orbit_data_sources=["ASF"],
    download_folder=TEST_DOWNLOAD_WORKSPACE,
    passes=True,
    exception_type=None,
    downloaded_scene_path=TEST_DOWNLOAD_WORKSPACE / f"{scene_1}.SAFE",
    downloaded_scene_url="https://datapool.asf.alaska.edu/SLC/SA/S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD.zip",
    downloaded_orbits_path=TEST_DOWNLOAD_WORKSPACE
    / f"S1A_OPER_AUX_POEORB_OPOD_20220121T121549_V20211231T225942_20220102T005942.EOF",
)

TEST_AUS_COP_HUB_DOWNLOAD = ProductDownloadTest(
    scene=scene_1,
    scene_data_sources=["AUS_COP_HUB"],
    unzip=True,
    orbit_data_sources=["AUS_COP_HUB"],
    download_folder=TEST_DOWNLOAD_WORKSPACE,
    passes=True,
    exception_type=None,
    downloaded_scene_path=TEST_DOWNLOAD_WORKSPACE / f"{scene_1}.SAFE",
    downloaded_scene_url="https://catalogue.copernicus.gov.au/odata/v1/Products(e948c832-d7e4-58d1-80d7-957b7f243371)",
    downloaded_orbits_path=TEST_DOWNLOAD_WORKSPACE
    / f"S1A_OPER_AUX_POEORB_OPOD_20220121T121549_V20211231T225942_20220102T005942.EOF",
)

TEST_NON_EXISTENT_PRODUCT = ProductDownloadTest(
    scene=scene_1 + "XX",  # non existing product name
    scene_data_sources=["CDSE", "ASF", "AUS_COP_HUB"],
    unzip=True,
    orbit_data_sources=["CDSE"],
    download_folder=TEST_DOWNLOAD_WORKSPACE,
    passes=False,
    exception_type=SceneDownloadError,
    downloaded_scene_path=None,
    downloaded_scene_url=None,
    downloaded_orbits_path=None,
)

TEST_NON_VALID_SCENE_DATA_SOURCE = ProductDownloadTest(
    scene=scene_1,
    scene_data_sources=["SPAGHETTI"],
    unzip=True,
    orbit_data_sources=["CDSE"],
    download_folder=TEST_DOWNLOAD_WORKSPACE,
    passes=False,
    exception_type=ValueError,
    downloaded_scene_path=None,
    downloaded_scene_url=None,
    downloaded_orbits_path=None,
)

TEST_CDSE_DOWNLOAD_S1D = ProductDownloadTest(
    scene=scene_2,
    scene_data_sources=["CDSE"],
    unzip=True,
    orbit_data_sources=["CDSE"],
    download_folder=TEST_DOWNLOAD_WORKSPACE,
    passes=True,
    exception_type=None,
    downloaded_scene_path=TEST_DOWNLOAD_WORKSPACE / f"{scene_2}.SAFE",
    downloaded_scene_url="https://download.dataspace.copernicus.eu/odata/v1/Products(8769d5b9-1db7-4a8d-b97b-d74f371b4e52)",
    downloaded_orbits_path=TEST_DOWNLOAD_WORKSPACE
    / f"S1D_OPER_AUX_RESORB_OPOD_20260420T223304_V20260420T183235_20260420T215005.EOF",
)

TEST_CASES = [
    TEST_AUS_COP_HUB_DOWNLOAD,
    TEST_CDSE_DOWNLOAD,
    TEST_ASF_DOWNLOAD,
    TEST_NON_EXISTENT_PRODUCT,
    TEST_NON_VALID_SCENE_DATA_SOURCE,
    TEST_CDSE_DOWNLOAD_S1D,
]


@pytest.mark.parametrize("test_case", TEST_CASES)
def test_product_downloads(test_case):

    # test cases we expect to pass
    if test_case.passes:

        # iterate through the preferences for the scene data source and download the scene
        SCENE_PATH, _, scene_url = download_scene_from_preference_list(
            scene_data_source_preferences=test_case.scene_data_sources,
            scene=test_case.scene,
            download_folder=test_case.download_folder,
            unzip=test_case.unzip,
        )

        logger.info(f"scene path : {SCENE_PATH}")
        logger.info(f"scene URL : {scene_url}")
        assert SCENE_PATH == test_case.downloaded_scene_path
        assert scene_url == test_case.downloaded_scene_url

        # download the orbits
        ORBIT_PATHS = download_orbits_from_preference_list(
            scene_safe_file=test_case.scene + ".SAFE",
            download_folder=test_case.download_folder,
            orbit_data_source_preferences=test_case.orbit_data_sources,
        )

        logger.info(f"orbit paths : {ORBIT_PATHS}")
        assert ORBIT_PATHS == test_case.downloaded_orbits_path

        shutil.rmtree(TEST_DOWNLOAD_WORKSPACE)

    else:
        with pytest.raises(test_case.exception_type):
            SCENE_PATH, _, scene_url = download_scene_from_preference_list(
                scene_data_source_preferences=test_case.scene_data_sources,
                scene=test_case.scene,
                download_folder=test_case.download_folder,
                unzip=test_case.unzip,
            )
