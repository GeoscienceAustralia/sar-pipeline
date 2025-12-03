from click.testing import CliRunner
from dataclasses import dataclass
from sar_pipeline.pipelines.isce3_rtc.cli import (
    make_rtc_opera_stac_and_upload_bursts,
    compare_products,
)
from sar_pipeline.utils.aws import S3Util
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
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_DEFAULT_REGION",
]
# check if the required env variables are set
identify_and_load_missing_env_vars(
    required_env_vars=REQUIRED_ENV_VARIABLES, dotenv_location=PROJECT_ROOT
)


@dataclass
class RunConfig:
    scene: str
    test_product_s3_bucket: Path
    test_product_s3_folder: Path
    original_local_product_folder: Path
    new_local_product_folder: Path
    compare_product_folder: Path
    product: str
    backscatter_convention: str
    collection_number: int
    s3_bucket: str
    s3_project_folder: str
    skip_upload_to_s3: str
    make_existing_products: bool
    link_static_layers: bool
    linked_static_layers_s3_bucket: bool
    linked_static_layers_collection_number: str
    linked_static_layers_s3_project_folder: str
    validate_stac: bool


from settings import (
    CURRENT_DIR,
    TEST_S3_BUCKET,
    TEST_1_SCENE,
    TEST_1_COLLECTION_NUMBER,
    TEST_1_BURST,
    TEST_1_COMPARE_RTC_S1_S3_PROJECT_FOLDER,
    PERSISTENT_S3_PROJECT_FOLDER,
)

ORIGINAL_PRODUCT_RESULTS_DIR = f"{CURRENT_DIR}/data/TMP/test_metadata/original"
NEW_PRODUCT_RESULTS_DIR = f"{CURRENT_DIR}/data/TMP/test_metadata/new"
COMPARE_PRODUCT_FOLDER = f"{CURRENT_DIR}/data/TMP/test_metadata/compare"
PRODUCT = "RTC_S1"

# custom test against another product by changing these values
# TEST_1_COLLECTION_NUMBER = 0
# TEST_1_BURST = "t085_182158_iw2"
# TEST_1_COMPARE_RTC_S1_S3_PROJECT_FOLDER = (
#     "experimental/baseline/antarctica/ga_s1_nrb_iw_hh_0/t085_182158_iw2/2021/04/25"
# )
# PERSISTENT_S3_PROJECT_FOLDER = "experimental/baseline/antarctica"

TEST_1 = RunConfig(
    scene=TEST_1_SCENE,
    test_product_s3_bucket=TEST_S3_BUCKET,
    test_product_s3_folder=TEST_1_COMPARE_RTC_S1_S3_PROJECT_FOLDER,
    original_local_product_folder=f"{ORIGINAL_PRODUCT_RESULTS_DIR}/TEST_1/RTC_S1/{TEST_1_BURST}",
    new_local_product_folder=f"{NEW_PRODUCT_RESULTS_DIR}/TEST_1/RTC_S1/{TEST_1_BURST}",
    compare_product_folder=f"{COMPARE_PRODUCT_FOLDER}/TEST_1/RTC_S1/{TEST_1_BURST}",
    product=PRODUCT,
    backscatter_convention="gamma0",
    collection_number=TEST_1_COLLECTION_NUMBER,
    s3_bucket=TEST_S3_BUCKET,
    s3_project_folder=PERSISTENT_S3_PROJECT_FOLDER,
    skip_upload_to_s3=True,
    make_existing_products=True,
    link_static_layers=True,
    linked_static_layers_s3_bucket=TEST_S3_BUCKET,
    linked_static_layers_collection_number=TEST_1_COLLECTION_NUMBER,
    linked_static_layers_s3_project_folder=PERSISTENT_S3_PROJECT_FOLDER,
    validate_stac=True,
)


@pytest.mark.parametrize("test_run", [TEST_1])
def test_cli_make_rtc_opera_stac_and_upload_bursts(test_run):

    # first download the test product to a local folder
    logger.info(
        f"Downloading test product to local folder : {test_run.original_local_product_folder}"
    )
    if Path(test_run.original_local_product_folder).exists():
        shutil.rmtree(test_run.original_local_product_folder)
    os.makedirs(test_run.original_local_product_folder, exist_ok=True)
    S3Downloader = S3Util()
    S3Downloader.download_folder(
        test_run.s3_bucket,
        test_run.test_product_s3_folder,
        test_run.original_local_product_folder,
    )

    logger.info(f"Copying product to new folder : {test_run.new_local_product_folder}")
    if Path(test_run.new_local_product_folder).exists():
        shutil.rmtree(test_run.new_local_product_folder)
    shutil.copytree(
        test_run.original_local_product_folder,
        test_run.new_local_product_folder,
    )

    # get the run-config
    run_config = list(Path(test_run.new_local_product_folder).glob("*config.yaml"))[0]
    # runs are at the scene level, so the results folder is the parent of the burst folder
    results_folder = Path(test_run.new_local_product_folder).parent
    # copy the run config to the parent
    shutil.copy(run_config, results_folder / run_config.name)
    run_config = results_folder / run_config.name

    runner = CliRunner()
    args = ["--results-folder", results_folder]
    args += ["--scene", test_run.scene]
    args += ["--run-config-path", run_config]
    args += ["--product", test_run.product]
    args += ["--backscatter-convention", test_run.backscatter_convention]
    args += ["--collection-number", test_run.collection_number]
    args += ["--s3-bucket", test_run.s3_bucket]
    args += ["--s3-project-folder", test_run.s3_project_folder]
    args += ["--skip-upload-to-s3"] if test_run.skip_upload_to_s3 else []
    args += ["--make-existing-products"] if test_run.make_existing_products else []
    args += ["--link-static-layers"] if test_run.link_static_layers else []
    args += ["--validate-stac"] if test_run.validate_stac else []

    logging.info(f"Running make_rtc_opera_stac_and_upload_bursts.")
    logging.info(
        f"Creating new metadata for the product stored at : {test_run.new_local_product_folder}."
    )
    result = runner.invoke(
        make_rtc_opera_stac_and_upload_bursts, args, catch_exceptions=True
    )
    if result.exception:
        logging.exception(
            "An error occurred during CLI invocation", exc_info=result.exception
        )
        logging.error(result.output)
    assert result.exit_code == 0
    logging.info(f"New metadata created.")


@pytest.mark.parametrize("test_run", [TEST_1])
def test_compare_new_product_with_original(test_run):

    logging.info(f"Comparing the original and new products to see changes in metadata")
    logging.info(
        f"Creating comparison outputs directory : {test_run.compare_product_folder}"
    )
    if Path(test_run.compare_product_folder).exists():
        shutil.rmtree(test_run.compare_product_folder)
    os.makedirs(test_run.compare_product_folder, exist_ok=True)

    runner = CliRunner()
    args = ["--product", "RTC_S1"]
    args += ["--local-product-folder-1", test_run.original_local_product_folder]
    args += ["--local-product-folder-2", test_run.new_local_product_folder]
    args += ["--out-folder", test_run.compare_product_folder]

    result = runner.invoke(compare_products, args, catch_exceptions=False)
    if result.exception:
        logging.exception(
            "An error occurred during CLI invocation", exc_info=result.exception
        )
        logging.error(result.output)

    assert result.exit_code == 0
