"""script to test sar_pipeline downloads of scenes and orbit files"""

from pathlib import Path
from dataclasses import dataclass
import logging
from dotenv import load_dotenv
import os
import pytest
import shutil

from sar_pipeline.aws.preparation.scenes import (
    download_scene_from_preference_list,
    SceneDownloadError,
)
from sar_pipeline.aws.preparation.orbits import (
    download_orbits,
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parent.parent
TEST_DOWNLOAD_WORKSPACE = CURRENT_DIR / Path("data/isce3_rtc/TMP/downloads")

REQUIRED_ENV_VARIABLES = [
    "EARTHDATA_LOGIN",
    "EARTHDATA_PASSWORD",
    "CDSE_LOGIN",
    "CDSE_PASSWORD",
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
        f"Attempting to load from env.secret file from the project root : {PROJECT_ROOT / "env.secret"}"
    )

    try:
        # load the environment secrets from a local file
        # see docs/workflows/aws.md for required variables
        # store in project root in env.secret file
        load_dotenv(PROJECT_ROOT / "env.secret")
        missing = [var for var in REQUIRED_ENV_VARIABLES if not os.getenv(var)]
        if missing:
            raise ValueError(
                f"env.secret was found but some variables are missing. The following environment variables must be set for test: {REQUIRED_ENV_VARIABLES}"
            )

    except:
        raise FileExistsError(
            "Could not find env.secret file at project root containing required environment variables for run. "
            "Create this file with required variables OR ensure environment is configured correctly "
            "(e.g. when running automated tests on GitHub)"
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

TEST_CDSE_DOWNLOAD = ProductDownloadTest(
    scene=scene_1,
    scene_data_sources=["CDSE"],
    unzip=True,
    orbit_data_sources=["CDSE"],
    download_folder=TEST_DOWNLOAD_WORKSPACE,
    passes=True,
    exception_type=None,
    downloaded_scene_path=TEST_DOWNLOAD_WORKSPACE / f"{scene_1}.SAFE",
    downloaded_scene_url="https://catalogue.dataspace.copernicus.eu/download/e948c832-d7e4-58d1-80d7-957b7f243371",
    downloaded_orbits_path=TEST_DOWNLOAD_WORKSPACE
    / f"S1A_OPER_AUX_POEORB_OPOD_20220121T121549_V20211231T225942_20220102T005942.EOF",
)

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
    orbit_data_sources=["CDSE"],
    download_folder=TEST_DOWNLOAD_WORKSPACE,
    passes=True,
    exception_type=None,
    downloaded_scene_path=TEST_DOWNLOAD_WORKSPACE / f"{scene_1}.SAFE",
    downloaded_scene_url="https://catalogue.copernicus.gov.au/odata/v1/Products(e948c832-d7e4-58d1-80d7-957b7f243371)",
    downloaded_orbits_path=TEST_DOWNLOAD_WORKSPACE
    / f"S1A_OPER_AUX_POEORB_OPOD_20220121T121549_V20211231T225942_20220102T005942.EOF",
)

TEST_NON_EXISTANT_PRODUCT = ProductDownloadTest(
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

TEST_CASES = [
    TEST_AUS_COP_HUB_DOWNLOAD,
    TEST_CDSE_DOWNLOAD,
    TEST_ASF_DOWNLOAD,
    TEST_NON_EXISTANT_PRODUCT,
    TEST_NON_VALID_SCENE_DATA_SOURCE,
]


@pytest.mark.parametrize("test_case", TEST_CASES)
def test_product_downloads(test_case):

    # if AUS_COP_HUB is selected, set the required environment variable'
    # pygssearch conda env is installed via pixi task in pyproject.toml
    if "AUS_COP_HUB" in test_case.scene_data_sources:
        os.environ["PYGSSEARCH_CONDA_ENV"] = str(
            Path(os.getenv("CONDA_EXE")).parent.parent / "envs" / "pygssearch-env"
        )
        logger.info(f"PYGSSEARCH_CONDA_ENV : {os.getenv("PYGSSEARCH_CONDA_ENV")}")

    # test casses we expect to pass
    if test_case.passes:

        # iterate through the preferences for the scene data source and download the scene
        SCENE_PATH, _, scene_url = download_scene_from_preference_list(
            scene_data_source_preferences=test_case.scene_data_sources,
            scene=test_case.scene,
            download_folder=test_case.download_folder,
            unzip=test_case.unzip,
        )

        assert SCENE_PATH == test_case.downloaded_scene_path
        assert scene_url == test_case.downloaded_scene_url

        # # download the orbits
        ORBIT_PATHS = download_orbits(
            scene_safe_file=test_case.scene + ".SAFE",
            save_dir=test_case.download_folder,
            source=test_case.orbit_data_sources,
        )

        logger.info(ORBIT_PATHS)
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
