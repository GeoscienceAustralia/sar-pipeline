from click.testing import CliRunner
from dataclasses import dataclass
from sar_pipeline.pipelines.isce3_rtc.cli import get_data_for_scene_and_make_run_config
from sar_pipeline.utils.environment_variables import identify_and_load_missing_env_vars
from pathlib import Path
from dotenv import load_dotenv
import os
import pytest
import shutil

import logging

logging.basicConfig(
    level=logging.DEBUG,  # or INFO
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parents[2]
TEST_WORKSPACE = CURRENT_DIR / Path("data")
REQUIRED_ENV_VARIABLES = [
    "EARTHDATA_LOGIN",
    "EARTHDATA_PASSWORD",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_DEFAULT_REGION",
    "CDSE_LOGIN",
    "CDSE_PASSWORD",
]
# check if the required env variables are set
identify_and_load_missing_env_vars(
    required_env_vars=REQUIRED_ENV_VARIABLES, dotenv_location=PROJECT_ROOT
)


@dataclass
class RunConfig:
    scene: str
    burst_id_list: str
    resolution: str
    output_crs: str
    dem_type: str
    product: str
    s3_bucket: str
    s3_project_folder: str
    collection_number: int
    download_folder: Path
    scratch_folder: Path
    out_folder: Path
    run_config_save_path: Path
    link_static_layers: bool
    linked_static_layers_s3_bucket: str
    linked_static_layers_collection_number: int
    linked_static_layers_s3_project_folder: str
    scene_data_source: str
    orbit_data_source: str


S3_PROJECT_FOLDER_T1 = "TEST"
COLLECTION_NUMBER_T1 = 1
SCENE_T1 = "S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD"
SUBPATH_T1 = Path(S3_PROJECT_FOLDER_T1) / str(COLLECTION_NUMBER_T1) / SCENE_T1
TEST_1 = RunConfig(
    scene=SCENE_T1,
    burst_id_list="t070_149815_iw3",
    resolution="20",
    output_crs="3031",
    dem_type="cop_glo30",
    product="RTC_S1",
    s3_bucket="deant-data-public-dev",
    s3_project_folder=S3_PROJECT_FOLDER_T1,
    collection_number=COLLECTION_NUMBER_T1,
    download_folder=TEST_WORKSPACE / "TMP" / "downloads",
    scratch_folder=TEST_WORKSPACE / "TMP" / "scratch" / SUBPATH_T1,
    out_folder=TEST_WORKSPACE / "TMP" / "results" / SUBPATH_T1,
    run_config_save_path=TEST_WORKSPACE
    / "TMP"
    / "results"
    / SUBPATH_T1
    / "OPERA-RTC_runconfig.yaml",
    link_static_layers=False,
    linked_static_layers_s3_bucket="",
    linked_static_layers_collection_number="",
    linked_static_layers_s3_project_folder="",
    scene_data_source="CDSE",
    orbit_data_source="CDSE",
)


@pytest.mark.parametrize("test_run", [TEST_1])
def test_get_data_for_scene_and_make_run_config(test_run):
    runner = CliRunner()
    args = ["--scene", test_run.scene]
    args += ["--burst-id-list", test_run.burst_id_list]
    args += ["--resolution", test_run.resolution]
    args += ["--output-crs", test_run.output_crs]
    args += ["--dem-type", test_run.dem_type]
    args += ["--product", test_run.product]
    args += ["--s3-bucket", test_run.s3_bucket]
    args += ["--s3-project-folder", test_run.s3_project_folder]
    args += ["--collection-number", test_run.collection_number]
    args += ["--download-folder", test_run.download_folder]
    args += ["--scratch-folder", test_run.scratch_folder]
    args += ["--out-folder", test_run.out_folder]
    args += ["--run-config-save-path", test_run.run_config_save_path]
    args += ["--link-static-layers"] if test_run.link_static_layers else []
    args += [
        "--linked-static-layers-s3-bucket",
        test_run.linked_static_layers_s3_bucket,
    ]
    args += [
        "--linked-static-layers-collection-number",
        test_run.linked_static_layers_collection_number,
    ]
    args += [
        "--linked-static-layers-s3-project-folder",
        test_run.linked_static_layers_s3_project_folder,
    ]
    args += [
        "--scene-data-source",
        test_run.scene_data_source,
    ]
    args += [
        "--orbit-data-source",
        test_run.orbit_data_source,
    ]

    logging.info(f"Running CLI, data will download. May take several minutes...")
    result = runner.invoke(
        get_data_for_scene_and_make_run_config, args, catch_exceptions=False
    )
    if result.exception:
        logging.exception(
            "An error occurred during CLI invocation", exc_info=result.exception
        )
        logging.error(result.output)
    # delete created folders after tests
    shutil.rmtree(test_run.scratch_folder)
    shutil.rmtree(test_run.download_folder)
    assert result.exit_code == 0
