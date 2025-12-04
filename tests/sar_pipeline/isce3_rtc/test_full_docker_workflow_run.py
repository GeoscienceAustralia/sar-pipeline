"""
Overview:
This is test for a complete build and run of the project docker image
It should be completed prior to every PR and release. A local run is generally
required, given the need for credentials, sufficient CPU, RAM and Disk Memory.
Recommend minimum of 4 CPU and 16 GB RAM.

The test is run for three scenes
- single pol HH scene over Antarctica
- dual pol VV+VH scene over Australia
- single pol scene over the Antimeridian.

The outputs of the run are compared to already created products in S3 to ensure
There are no unexpected changes in data and metadata.

Test steps:
1.  Required environment variables are set.
2.  The docker image for the current state is built and tagged.
3.  The container is run, creating static layers (RTC_S1_STATIC) and uploading them to a
    temporary folder in the AWS `TEST_S3_BUCKET` and `TEST_S3_PROJECT_FOLDER` set below.
4. The container is run again for backscatter products (RTC_S1), linking them to the
    RTC_S1_STATIC products made in the previous step. The results are then uploaded to AWS.
5. The newly created products are compared to those stored at the PERSISTENT_S3_PROJECT_FOLDER to understand
    any differences that have been made (e.g. breaking differences in geotiff data and changes in metadata).
6. Steps 3, 4 and 5 are completed for each scene listed above.

Creating / updating new test data:
1. In step 5 above, the created products are compared to existing products that are stored
   in the PERSISTENT_S3_PROJECT_FOLDER. If planned product changes have been made, these
   comparison products should be updated for future tests. These can be replaced by new products
   by setting the UPDATE_PERSISTENT_TEST_DATA to True in the settings.py file and re-running the tests.
   NOTE - existing products should be manually deleted from the PERSISTENT_S3_PROJECT_FOLDER prior
   to recreating them.
"""

import subprocess
import pytest
import os
import logging
from pathlib import Path
import sys
from datetime import datetime
import sar_pipeline
from sar_pipeline.pipelines.isce3_rtc.cli import compare_products
from sar_pipeline.analysis.compare_cog import check_tifs_have_changed
from sar_pipeline.analysis.compare_folder import check_files_have_changed
from sar_pipeline.utils.environment_variables import identify_and_load_missing_env_vars
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
    UPDATE_PERSISTENT_TEST_DATA,
)

if UPDATE_PERSISTENT_TEST_DATA:
    logger.warning(
        f"Updating the persistent data used for the test comparisons. Ensure existing products are deleted."
    )
    TEST_S3_PROJECT_FOLDER = PERSISTENT_S3_PROJECT_FOLDER

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
# optional env variables to be passed to docker run if existing
OPTIONAL_ENV_VARIABLES = [
    "AWS_SESSION_TOKEN",
    "AWS_CREDENTIAL_EXPIRATION",
    "AWS_SESSION_EXPIRATION",
]
# check if the required env variables are set
identify_and_load_missing_env_vars(
    required_env_vars=REQUIRED_ENV_VARIABLES, dotenv_location=PROJECT_ROOT
)

# set the environment variables as string for docker
# missing optional vars will not be added
ENV_VARS = []
for var in REQUIRED_ENV_VARIABLES + OPTIONAL_ENV_VARIABLES:
    if os.getenv(var):
        ENV_VARS.append("-e")
        ENV_VARS.append(f"{var}={os.getenv(var)}")


@pytest.fixture(scope="module", autouse=True)
def build_image():
    """build and tag the docker image for the current codebase to be used in tests"""
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
    """Run the docker image and create a burst product for a single pol SLC. First,
    static layers (RTC_S1_STATIC) are created. Then, NRB (RTC_S1) products are created
    that get linked to the previous static layers.
    """
    logging.info(f"Running full process for single pol (HH), this may take a while...")
    logging.info(f"Static layers will be produced and linked to backscatter data.")
    if not Path(LOCAL_TEST_OUTPUTS_DIR).exists():
        os.makedirs(LOCAL_TEST_OUTPUTS_DIR)
    logging.info(f"Saving test outputs locally to : {LOCAL_TEST_OUTPUTS_DIR}")
    logging.info(f"Uploading outputs to : {TEST_S3_BUCKET}/{TEST_S3_PROJECT_FOLDER}")
    logging.info(
        "Mounting test data directory for results: "
        f"{LOCAL_TEST_OUTPUTS_DIR}:/home/rtc_user/working/results",
    )
    logging.info(f"RUN 1: Producing Static Layers (RTC_S1_STATIC)")
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

    logging.info(f"RUN 2: Producing Backscatter (RTC_S1) and Linking to Static Layers")
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
    This function will compare the static layer outputs (RTC_S1_STATIC) created in the test_docker_single_pol_with_args
    function with existing outputs in AWS. The output of this are data that describe
    the differences in product files, metadata (.json and xml) and in the GeoTiffs themselves.
    These outputs can be used to understand if the changes made are planned and acceptable.
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
    assert not check_files_have_changed(
        file_differences
    ), f"Error, there are breaking changes in the test files compared to the comparison product. \
    Check {file_differences} and update comparison products if needed."
    assert not check_tifs_have_changed(
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
    This function will compare the RTC_S1 outputs created in the test_docker_single_pol_with_args
    function with existing outputs in AWS. The output of this are data that describe
    the differences in product files, metadata (.json and xml) and in the GeoTiffs themselves.
    These outputs can be used to understand if the changes made are planned and acceptable.
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
    assert not check_files_have_changed(
        file_differences
    ), f"Error, there are breaking changes in the test files compared to the comparison product. \
    Check {file_differences} and update comparison products if needed."
    assert not check_tifs_have_changed(
        tif_differences
    ), f"Error, the created tif values have changed compared to the comparison product. \
    Check {tif_differences} and update comparison products if needed."


def test_docker_dual_pol_with_args():
    """Run the docker image and create a burst product for a dual pol SLC. First,
    static layers (RTC_S1_STATIC) are created. Then, NRB (RTC_S1) products are created
    that get linked to the previous static layers.
    """
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
    This function will compare the RTC_S1_STATIC outputs created in the test_docker_dual_pol_with_args
    function with existing outputs in AWS. The output of this are data that describe
    the differences in product files, metadata (.json and xml) and in the GeoTiffs themselves.
    These outputs can be used to understand if the changes made are planned and acceptable.
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
    assert not check_files_have_changed(
        file_differences
    ), f"Error, there are breaking changes in the test files compared to the comparison product. \
    Check {file_differences} and update comparison products if needed."
    assert not check_tifs_have_changed(
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
    This function will compare the RTC_S1 outputs created in the test_docker_dual_pol_with_args
    function with existing outputs in AWS. The output of this are data that describe
    the differences in product files, metadata (.json and xml) and in the GeoTiffs themselves.
    These outputs can be used to understand if the changes made are planned and acceptable.
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
    assert not check_files_have_changed(
        file_differences
    ), f"Error, there are breaking changes in the test files compared to the comparison product. \
    Check {file_differences} and update comparison products if needed."
    assert not check_tifs_have_changed(
        tif_differences
    ), f"Error, the created tif values have changed compared to the comparison product. \
    Check {tif_differences} and update comparison products if needed."
