"""
Overview:
This is test for a complete build and run of the project docker image
It should be completed prior to every PR and release. A local run is generally
required, given the need for credentials, sufficient CPU, RAM and Disk Memory.
Recommend minimum of 4 CPU and 16 GB RAM.

Test steps:
1.  Required environment variables are set.
2.  The docker image for the current state is built and tagged.
3.  The container is run, creating static layers (RTC_S1_STATIC) and uploading them to a
    temporary folder in the AWS `TEST_S3_BUCKET` and `TEST_S3_PROJECT_FOLDER` set below
4. The container is run again for the backscatter products (RTC_S1), linking them to the
    RTC_S1_STATIC products made in the above step. The results are similarly uploaded to AWS.
5. The newly created products are compared to those stored at the PERSISTENT_S3_PROJECT_FOLDER to understand
    any differences that have been made.
6. Steps 3, 4 and 5 are completed for a single pol (HH) and dual pol (VV+VH) scene burst.

Creating / updating new test data:
1. In step 5 above, the created products are compared to existing products that are stored
   in the PERSISTENT_S3_PROJECT_FOLDER below. If planned product changes have been made,
   these comparison products should be updated for future tests. These can be replaced by new
   products by uncommenting the line TEST_S3_PROJECT_FOLDER = PERSISTENT_S3_PROJECT_FOLDER below
   and re-running the tests. This will upload the products created in the tests to the
   PERSISTENT_S3_PROJECT_FOLDER, and replace what is there.

"""

import subprocess
import pytest
import os
import logging
from pathlib import Path
from dotenv import load_dotenv
import sys
from datetime import datetime
import sar_pipeline
from sar_pipeline.pipelines.isce3_rtc.cli import compare_products
from click.testing import CliRunner
import re
import json

logging.basicConfig(
    level=logging.DEBUG,  # or INFO
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

# Directories
CURRENT_DIR = Path(__file__).parent.resolve()
LOCAL_TEST_OUTPUTS_DIR = f"{CURRENT_DIR}/data/TMP/results"
LOCAL_COMPARISON_OUTPUTS_DIR = f"{CURRENT_DIR}/data/TMP/compare"
PROJECT_ROOT = CURRENT_DIR.parents[2]

# shared test values
DOCKER_TAG = re.sub(r"[^a-zA-Z0-9_.-]", "-", sar_pipeline.__version__)
RUN_DATETIME = str(datetime.now()).replace(" ", "_").replace(":", "-")
TEST_NAME = Path(__file__).stem
TEST_S3_PROJECT_FOLDER = f"TMP/sar-pipeline/isce3_rtc/{RUN_DATETIME}/{TEST_NAME}"

# test information
from settings import (
    TEST_1_SCENE,
    TEST_1_BURST,
    TEST_1_S3_RTC_S1_STATIC_PRODUCT_SUBPATH,
    TEST_1_S3_RTC_S1_PRODUCT_SUBPATH,
    TEST_2_SCENE,
    TEST_2_BURST,
    TEST_2_S3_RTC_S1_STATIC_PRODUCT_SUBPATH,
    TEST_2_S3_RTC_S1_PRODUCT_SUBPATH,
    TEST_S3_BUCKET,
    PERSISTENT_S3_PROJECT_FOLDER,
)

# UNCOMMENT THIS LINE TO UPDATE TEST PRODUCTS WITH NEW PRODUCTS
# TEST_S3_PROJECT_FOLDER = PERSISTENT_S3_PROJECT_FOLDER

REQUIRED_ENV_VARIABLES = [
    "EARTHDATA_LOGIN",
    "EARTHDATA_PASSWORD",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_DEFAULT_REGION",
    "CDSE_LOGIN",
    "CDSE_PASSWORD",
    "AUS_COP_HUB_LOGIN",
    "AUS_COP_HUB_PASSWORD",
    "AUS_COP_HUB_CLIENT_ID",
    "AUS_COP_HUB_CLIENT_SECRET",
]
# check if the required env variables are set
missing = [var for var in REQUIRED_ENV_VARIABLES if not os.getenv(var)]

if not missing:
    ENV_VARS = []
    for var in REQUIRED_ENV_VARIABLES:
        ENV_VARS.append("-e")
        ENV_VARS.append(f"{var}={os.getenv(var)}")

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
                ".env was found but some variables are missing. Add the required variables."
            )
        else:
            logging.info("Environment variables loaded from .env successfully.")
            ENV_VARS = ["--env-file", f'{PROJECT_ROOT / ".env"}']

    except:
        raise FileExistsError(
            "Could not find .env file at project root containing required environment variables for run. "
            "Create this file with required variables OR ensure environment is configured correctly "
            "(e.g. when running automated tests on GitHub)"
        )


def _files_have_changed(file_difference_json_path) -> bool:
    """checks the outputs of the file difference json to see if
    the files have changed"""
    with open(file_difference_json_path, "r") as f:
        data = json.load(f)

    # Loop through each entry and check
    for entry in data:
        missing_1 = entry["in_folder_1_missing_in_folder_2"]
        missing_2 = entry["in_folder_2_missing_in_folder_1"]
        if missing_1 or missing_2:
            # we have file differences
            return True
    return False


def _tifs_have_changed(tif_difference_json_path) -> bool:
    """checks the outputs of the tif difference json to see if
    the tif values have changed"""
    with open(tif_difference_json_path, "r") as f:
        data = json.load(f)

    # Loop through the assets that are being compared to see if
    # Any of the tif statistics have changed
    for asset in data.keys():
        stats_are_equal = data[asset]["stats_are_equal"]
        # get the list of equalities (i.e. True or False)
        stats_are_equal = [stats_are_equal[k] for k in stats_are_equal.keys()]
        if any(x is False for x in stats_are_equal):
            return True
    return False


@pytest.fixture(scope="module", autouse=True)
def build_image():
    logging.info(
        f"Building docker image sar-pipeline:{DOCKER_TAG} for testing, this may take a few minutes..."
    )
    result = subprocess.run(
        [
            "docker",
            "build",
            "-t",
            f"sar-pipeline:{DOCKER_TAG}",
            "-f",
            "Docker/isce3_rtc/Dockerfile",
            ".",
        ],
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True,
    )
    assert (
        result.returncode == 0
    ), f"Docker build failed: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"


def test_docker_single_pol_with_args():
    logging.info(f"Running full process for single pol (HH), this may take a while...")
    logging.info(f"Static layers will be produced and linked to backscatter data.")
    if not Path(LOCAL_TEST_OUTPUTS_DIR).exists():
        os.makedirs(LOCAL_TEST_OUTPUTS_DIR)
    logging.info(f"Saving test outputs locally to : {LOCAL_TEST_OUTPUTS_DIR}")
    logging.info(f"Uploading outputs to : {TEST_S3_BUCKET}/{TEST_S3_PROJECT_FOLDER}")
    logging.info(f"RUN 1: Producing Static Layers")
    logging.info(
        "Mounting test data directory for results: "
        f"{LOCAL_TEST_OUTPUTS_DIR}:/home/rtc_user/working/results",
    )
    cmd = [
        "docker",
        "run",
        "-v",
        f"{LOCAL_TEST_OUTPUTS_DIR}:/home/rtc_user/working/results",
        "--rm",
        *ENV_VARS,
        f"sar-pipeline:{DOCKER_TAG}",
        "--scene",
        TEST_1_SCENE,
        "--burst_id_list",
        TEST_1_BURST,
        "--product",
        "RTC_S1_STATIC",
        "--backscatter_convention",
        "gamma0",
        "--collection_number",
        "1",
        "--s3_bucket",
        TEST_S3_BUCKET,
        "--s3_project_folder",
        TEST_S3_PROJECT_FOLDER,
    ]
    result = subprocess.run(
        cmd,
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True,
    )
    assert (
        result.returncode == 0
    ), f"Non-zero exit code: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

    logging.info(f"RUN 2: Producing Backscatter and Linking to Static Layers")
    cmd = [
        "docker",
        "run",
        "-v",
        f"{LOCAL_TEST_OUTPUTS_DIR}:/home/rtc_user/working/results",
        "--rm",
        *ENV_VARS,
        f"sar-pipeline:{DOCKER_TAG}",
        "--scene",
        TEST_1_SCENE,
        "--burst_id_list",
        TEST_1_BURST,
        "--product",
        "RTC_S1",
        "--backscatter_convention",
        "gamma0",
        "--collection_number",
        "1",
        "--s3_bucket",
        TEST_S3_BUCKET,
        "--s3_project_folder",
        TEST_S3_PROJECT_FOLDER,
        "--link_static_layers",
        "--linked_static_layers_s3_project_folder",
        TEST_S3_PROJECT_FOLDER,
        "--linked_static_layers_collection_number",
        "1",
    ]

    result = subprocess.run(
        cmd,
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True,
    )
    assert (
        result.returncode == 0
    ), f"Non-zero exit code: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"


# folders for products to compare
TEST_1_RTC_S1_STATIC_S3_PROJECT_FOLDER = (
    f"{TEST_S3_PROJECT_FOLDER}/{TEST_1_S3_RTC_S1_STATIC_PRODUCT_SUBPATH}"
)
TEST_1_COMPARE_RTC_S1_STATIC_S3_PROJECT_FOLDER = (
    f"{PERSISTENT_S3_PROJECT_FOLDER}/{TEST_1_S3_RTC_S1_STATIC_PRODUCT_SUBPATH}"
)
TEST_1_RTC_S1_STATIC_LOCAL_COMPARISON_OUTPUTS_DIR = (
    f"{LOCAL_COMPARISON_OUTPUTS_DIR}/TEST_1_RTC_S1_STATIC"
)


def test_compare_single_pol_rtc_s1_static_product_outputs():
    """
    This function will compare the outputs created in the test_docker_single_pol_with_args
    function with existing outputs in AWS. The output of this are data that describe
    the differences in product files, metadata (.json and xml) and in the tifs themselves.
    These outputs can be used to understand if the changes made are acceptable.
    """
    logging.info(
        f"COMPARE 1: Comparing created Static Layers with Existing Accepted Product"
    )

    logging.info(
        f"Creating comparison outputs directory : {TEST_1_RTC_S1_STATIC_LOCAL_COMPARISON_OUTPUTS_DIR}"
    )
    os.makedirs(TEST_1_RTC_S1_STATIC_LOCAL_COMPARISON_OUTPUTS_DIR, exist_ok=True)

    runner = CliRunner()
    args = ["--product", "RTC_S1_STATIC"]
    args += ["--s3-product-folder-1", TEST_1_RTC_S1_STATIC_S3_PROJECT_FOLDER]
    args += ["--s3-product-folder-2", TEST_1_COMPARE_RTC_S1_STATIC_S3_PROJECT_FOLDER]
    args += ["--s3-bucket", TEST_S3_BUCKET]
    args += ["--out-folder", TEST_1_RTC_S1_STATIC_LOCAL_COMPARISON_OUTPUTS_DIR]

    result = runner.invoke(compare_products, args, catch_exceptions=False)
    if result.exception:
        logging.exception(
            "An error occurred during CLI invocation", exc_info=result.exception
        )
        logging.error(result.output)

    assert result.exit_code == 0

    # ensure that the files and tif values have not changed. If so, these are breaking changes to the
    # product, and the persistent comparison products must be updated - see description at top
    file_differences = (
        f"{TEST_1_RTC_S1_STATIC_LOCAL_COMPARISON_OUTPUTS_DIR}/file_differences.json"
    )
    tif_differences = (
        f"{TEST_1_RTC_S1_STATIC_LOCAL_COMPARISON_OUTPUTS_DIR}/tif_differences.json"
    )
    assert not _files_have_changed(
        file_differences
    ), f"Error, there are breaking changes in the test files compared to the comparison product. \
    Check {file_differences} and update comparison products if needed."
    assert not _tifs_have_changed(
        tif_differences
    ), f"Error, the created tif values have changed compared to the comparison product. \
    Check {tif_differences} and update comparison products if needed."


# folders for products to compare
TEST_1_RTC_S1_S3_PROJECT_FOLDER = (
    f"{TEST_S3_PROJECT_FOLDER}/{TEST_1_S3_RTC_S1_PRODUCT_SUBPATH}"
)
TEST_1_COMPARE_RTC_S1_S3_PROJECT_FOLDER = (
    f"{PERSISTENT_S3_PROJECT_FOLDER}/{TEST_1_S3_RTC_S1_PRODUCT_SUBPATH}"
)
TEST_1_RTC_S1_LOCAL_COMPARISON_OUTPUTS_DIR = (
    f"{LOCAL_COMPARISON_OUTPUTS_DIR}/TEST_1_RTC_S1"
)


def test_compare_single_pol_rtc_s1_product_outputs():
    """
    This function will compare the outputs created in the test_docker_single_pol_with_args
    function with existing outputs in AWS. The output of this are data that describe
    the differences in product files, metadata (.json and xml) and in the tifs themselves.
    These outputs can be used to understand if the changes made are acceptable.
    """

    logging.info(
        f"COMPARE 2: Comparing created Backscatter Product with Existing Accepted Product"
    )
    logging.info(
        f"Creating comparison outputs directory : {TEST_1_RTC_S1_LOCAL_COMPARISON_OUTPUTS_DIR}"
    )
    os.makedirs(TEST_1_RTC_S1_LOCAL_COMPARISON_OUTPUTS_DIR, exist_ok=True)

    runner = CliRunner()
    args = ["--product", "RTC_S1"]
    args += ["--s3-product-folder-1", TEST_1_RTC_S1_S3_PROJECT_FOLDER]
    args += ["--s3-product-folder-2", TEST_1_COMPARE_RTC_S1_S3_PROJECT_FOLDER]
    args += ["--s3-bucket", TEST_S3_BUCKET]
    args += ["--out-folder", TEST_1_RTC_S1_LOCAL_COMPARISON_OUTPUTS_DIR]

    result = runner.invoke(compare_products, args, catch_exceptions=False)
    if result.exception:
        logging.exception(
            "An error occurred during CLI invocation", exc_info=result.exception
        )
        logging.error(result.output)

    assert result.exit_code == 0

    # ensure that the files and tif values have not changed. If so, these are breaking changes to the
    # product, and the persistent comparison products must be updated - see description at top
    file_differences = (
        f"{TEST_1_RTC_S1_LOCAL_COMPARISON_OUTPUTS_DIR}/file_differences.json"
    )
    tif_differences = (
        f"{TEST_1_RTC_S1_LOCAL_COMPARISON_OUTPUTS_DIR}/tif_differences.json"
    )
    assert not _files_have_changed(
        file_differences
    ), f"Error, there are breaking changes in the test files compared to the comparison product. \
    Check {file_differences} and update comparison products if needed."
    assert not _tifs_have_changed(
        tif_differences
    ), f"Error, the created tif values have changed compared to the comparison product. \
    Check {tif_differences} and update comparison products if needed."


def test_docker_dual_pol_with_args():
    logging.info(f"Running full process for dual pol (VV+VH), this may take a while...")
    logging.info(f"Static layers will be produced and linked to backscatter data.")
    if not Path(LOCAL_TEST_OUTPUTS_DIR).exists():
        os.makedirs(LOCAL_TEST_OUTPUTS_DIR)
    logging.info(f"Saving test outputs locally to : {LOCAL_TEST_OUTPUTS_DIR}")
    logging.info(f"Uploading outputs to : {TEST_S3_BUCKET}/{TEST_S3_PROJECT_FOLDER}")
    logging.info(f"RUN 1: Producing Static Layers")
    logging.info(
        "Mounting test data directory for results: "
        f"{LOCAL_TEST_OUTPUTS_DIR}:/home/rtc_user/working/results",
    )
    cmd = [
        "docker",
        "run",
        "-v",
        f"{LOCAL_TEST_OUTPUTS_DIR}:/home/rtc_user/working/results",
        "--rm",
        *ENV_VARS,
        f"sar-pipeline:{DOCKER_TAG}",
        "--scene",
        TEST_2_SCENE,
        "--burst_id_list",
        TEST_2_BURST,
        "--product",
        "RTC_S1_STATIC",
        "--backscatter_convention",
        "gamma0",
        "--collection_number",
        "1",
        "--s3_bucket",
        TEST_S3_BUCKET,
        "--s3_project_folder",
        TEST_S3_PROJECT_FOLDER,
    ]
    result = subprocess.run(
        cmd,
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True,
    )
    assert (
        result.returncode == 0
    ), f"Non-zero exit code: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

    logging.info(f"RUN 2: Producing Backscatter and Linking to Static Layers")
    cmd = [
        "docker",
        "run",
        "-v",
        f"{LOCAL_TEST_OUTPUTS_DIR}:/home/rtc_user/working/results",
        "--rm",
        *ENV_VARS,
        f"sar-pipeline:{DOCKER_TAG}",
        "--scene",
        TEST_2_SCENE,
        "--burst_id_list",
        TEST_2_BURST,
        "--product",
        "RTC_S1",
        "--backscatter_convention",
        "gamma0",
        "--collection_number",
        "1",
        "--s3_bucket",
        TEST_S3_BUCKET,
        "--s3_project_folder",
        TEST_S3_PROJECT_FOLDER,
        "--link_static_layers",
        "--linked_static_layers_s3_project_folder",
        TEST_S3_PROJECT_FOLDER,
        "--linked_static_layers_collection_number",
        "1",
    ]

    result = subprocess.run(
        cmd,
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True,
    )
    assert (
        result.returncode == 0
    ), f"Non-zero exit code: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"


# folders for products to compare
TEST_2_RTC_S1_STATIC_S3_PROJECT_FOLDER = (
    f"{TEST_S3_PROJECT_FOLDER}/{TEST_2_S3_RTC_S1_STATIC_PRODUCT_SUBPATH}"
)
TEST_2_COMPARE_RTC_S1_STATIC_S3_PROJECT_FOLDER = (
    f"{PERSISTENT_S3_PROJECT_FOLDER}/{TEST_2_S3_RTC_S1_STATIC_PRODUCT_SUBPATH}"
)
TEST_2_RTC_S1_STATIC_LOCAL_COMPARISON_OUTPUTS_DIR = (
    f"{LOCAL_COMPARISON_OUTPUTS_DIR}/TEST_2_RTC_S1_STATIC"
)


def test_compare_dual_pol_rtc_s1_static_product_outputs():
    """
    This function will compare the outputs created in the test_docker_single_pol_with_args
    function with existing outputs in AWS. The output of this are data that describe
    the differences in product files, metadata (.json and xml) and in the tifs themselves.
    These outputs can be used to understand if the changes made are acceptable.
    """

    logging.info(
        f"COMPARE 1: Comparing created Static Layers with Existing Accepted Product"
    )
    logging.info(
        f"Creating comparison outputs directory : {TEST_2_RTC_S1_STATIC_LOCAL_COMPARISON_OUTPUTS_DIR}"
    )
    os.makedirs(TEST_2_RTC_S1_STATIC_LOCAL_COMPARISON_OUTPUTS_DIR, exist_ok=True)

    runner = CliRunner()
    args = ["--product", "RTC_S1_STATIC"]
    args += ["--s3-product-folder-1", TEST_2_RTC_S1_STATIC_S3_PROJECT_FOLDER]
    args += ["--s3-product-folder-2", TEST_2_COMPARE_RTC_S1_STATIC_S3_PROJECT_FOLDER]
    args += ["--s3-bucket", TEST_S3_BUCKET]
    args += ["--out-folder", TEST_2_RTC_S1_STATIC_LOCAL_COMPARISON_OUTPUTS_DIR]

    result = runner.invoke(compare_products, args, catch_exceptions=False)
    if result.exception:
        logging.exception(
            "An error occurred during CLI invocation", exc_info=result.exception
        )
        logging.error(result.output)

    assert result.exit_code == 0

    # ensure that the files and tif values have not changed. If so, these are breaking changes to the
    # product, and the persistent comparison products must be updated - see description at top
    file_differences = (
        f"{TEST_2_RTC_S1_STATIC_LOCAL_COMPARISON_OUTPUTS_DIR}/file_differences.json"
    )
    tif_differences = (
        f"{TEST_2_RTC_S1_STATIC_LOCAL_COMPARISON_OUTPUTS_DIR}/tif_differences.json"
    )
    assert not _files_have_changed(
        file_differences
    ), f"Error, there are breaking changes in the test files compared to the comparison product. \
    Check {file_differences} and update comparison products if needed."
    assert not _tifs_have_changed(
        tif_differences
    ), f"Error, the created tif values have changed compared to the comparison product. \
    Check {tif_differences} and update comparison products if needed."


# folders for products to compare
TEST_2_RTC_S1_S3_PROJECT_FOLDER = (
    f"{TEST_S3_PROJECT_FOLDER}/{TEST_2_S3_RTC_S1_PRODUCT_SUBPATH}"
)
TEST_2_COMPARE_RTC_S1_S3_PROJECT_FOLDER = (
    f"{PERSISTENT_S3_PROJECT_FOLDER}/{TEST_2_S3_RTC_S1_PRODUCT_SUBPATH}"
)
TEST_2_RTC_S1_LOCAL_COMPARISON_OUTPUTS_DIR = (
    f"{LOCAL_COMPARISON_OUTPUTS_DIR}/TEST_2_RTC_S1"
)


def test_compare_dual_pol_rtc_s1_product_outputs():
    """
    This function will compare the outputs created in the test_docker_single_pol_with_args
    function with existing outputs in AWS. The output of this are data that describe
    the differences in product files, metadata (.json and xml) and in the tifs themselves.
    These outputs can be used to understand if the changes made are acceptable.
    """

    logging.info(
        f"COMPARE 2: Comparing created Backscatter Product with Existing Accepted Product"
    )
    logging.info(
        f"Creating comparison outputs directory : {TEST_2_RTC_S1_LOCAL_COMPARISON_OUTPUTS_DIR}"
    )
    os.makedirs(TEST_2_RTC_S1_LOCAL_COMPARISON_OUTPUTS_DIR, exist_ok=True)

    runner = CliRunner()
    args = ["--product", "RTC_S1"]
    args += ["--s3-product-folder-1", TEST_2_RTC_S1_S3_PROJECT_FOLDER]
    args += ["--s3-product-folder-2", TEST_2_COMPARE_RTC_S1_S3_PROJECT_FOLDER]
    args += ["--s3-bucket", TEST_S3_BUCKET]
    args += ["--out-folder", TEST_2_RTC_S1_LOCAL_COMPARISON_OUTPUTS_DIR]

    result = runner.invoke(compare_products, args, catch_exceptions=False)
    if result.exception:
        logging.exception(
            "An error occurred during CLI invocation", exc_info=result.exception
        )
        logging.error(result.output)

    assert result.exit_code == 0

    # ensure that the files and tif values have not changed. If so, these are breaking changes to the
    # product, and the persistent comparison products must be updated - see description at top
    file_differences = (
        f"{TEST_2_RTC_S1_LOCAL_COMPARISON_OUTPUTS_DIR}/file_differences.json"
    )
    tif_differences = (
        f"{TEST_2_RTC_S1_LOCAL_COMPARISON_OUTPUTS_DIR}/tif_differences.json"
    )
    assert not _files_have_changed(
        file_differences
    ), f"Error, there are breaking changes in the test files compared to the comparison product. \
    Check {file_differences} and update comparison products if needed."
    assert not _tifs_have_changed(
        tif_differences
    ), f"Error, the created tif values have changed compared to the comparison product. \
    Check {tif_differences} and update comparison products if needed."
