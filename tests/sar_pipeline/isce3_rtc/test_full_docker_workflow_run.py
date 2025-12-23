"""
Overview:
This is test for a complete build and run of the project docker image.
It should be completed prior to every release. A local run is generally
required, given the need for credentials, sufficient CPU, RAM and Disk Memory.
Recommend minimum of 4 CPU and 16 GB RAM.

The test is run for three scenes
- single pol HH scene over Antarctica
- dual pol VV+VH scene over Australia
- single pol scene over the Antimeridian (Antarctica).

The outputs of the run are compared to already created products in S3 to ensure
There are no unexpected changes in data and metadata.

Test steps:
1.  Required environment variables are set. A .env file in the project root can be used.
2.  The docker image for the current state is built and tagged.
3.  The container is run, creating static layers (RTC_S1_STATIC) and uploading them to a
    temporary folder in the AWS `TEST_S3_BUCKET` and `TEST_S3_PROJECT_FOLDER` set below.
4. The container is run again for backscatter products (RTC_S1), linking them to the
    RTC_S1_STATIC products made in the previous step. The results are then uploaded to AWS.
5. The newly created products are compared to benchmark products stored at the
    BENCHMARK_S3_PROJECT_FOLDER to understand any differences that have been introduced (e.g.
    breaking differences in Geotiff data and changes in metadata).
6. Steps 3, 4 and 5 are completed for each scene listed above.

Creating and updating the benchmark test data:
1. In step 5 above, the created products are compared to existing products that are stored
   in the BENCHMARK_S3_PROJECT_FOLDER. If planned product changes have been made, these benchmark
   comparison products should be updated for future tests. These can be replaced by new products
   by setting the UPDATE_BENCHMARK_TEST_DATA to True in the settings.py file and re-running the tests.
   NOTE - existing products should be manually deleted from the BENCHMARK_S3_PROJECT_FOLDER prior
   to recreating them.
"""

import subprocess
import pytest
import os
import logging
from pathlib import Path
import sys
from datetime import datetime
from typing import Literal
import re

import sar_pipeline
from sar_pipeline.utils.environment_variables import identify_and_load_missing_env_vars
from sar_pipeline.pipelines.isce3_rtc.cli import compare_products
from sar_pipeline.analysis.compare_cog import check_tifs_have_changed
from sar_pipeline.analysis.compare_folder import check_files_have_changed
from click.testing import CliRunner

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
# DOCKER_TAG = '0.4.1.dev36-g6eecb22a7.d20250925' # set existing image
RUN_DATETIME = str(datetime.now()).replace(" ", "_").replace(":", "-")
# RUN_DATETIME = '2025-12-04_05-46-40.829598'  # set existing datetime
TEST_NAME = Path(__file__).stem
TEST_S3_PROJECT_FOLDER = f"TMP/sar-pipeline/isce3_rtc/{RUN_DATETIME}/{TEST_NAME}"

# test information
from settings import (
    BENCHMARK_S3_PROJECT_FOLDER,
    UPDATE_BENCHMARK_TEST_DATA,
    TEST_1_SCENE,
    TEST_1_BURST,
    TEST_1_RTC_S1_STATIC_PRODUCT_S3_PREFIX,
    TEST_1_RTC_S1_PRODUCT_S3_PREFIX,
    TEST_1_BENCHMARK_RTC_S1_S3_PRODUCT_FOLDER,
    TEST_1_BENCHMARK_RTC_S1_STATIC_S3_PRODUCT_FOLDER,
    TEST_2_SCENE,
    TEST_2_BURST,
    TEST_2_RTC_S1_STATIC_PRODUCT_S3_PREFIX,
    TEST_2_RTC_S1_PRODUCT_S3_PREFIX,
    TEST_2_BENCHMARK_RTC_S1_S3_PRODUCT_FOLDER,
    TEST_2_BENCHMARK_RTC_S1_STATIC_S3_PRODUCT_FOLDER,
    TEST_3_SCENE,
    TEST_3_BURST,
    TEST_3_RTC_S1_STATIC_PRODUCT_S3_PREFIX,
    TEST_3_RTC_S1_PRODUCT_S3_PREFIX,
    TEST_3_BENCHMARK_RTC_S1_S3_PRODUCT_FOLDER,
    TEST_3_BENCHMARK_RTC_S1_STATIC_S3_PRODUCT_FOLDER,
    TEST_S3_BUCKET,
)

if UPDATE_BENCHMARK_TEST_DATA:
    logger.warning(
        f"Updating the benchmark/persistent data used for the test comparisons. "
        " Ensure existing products are deleted."
    )
    TEST_S3_PROJECT_FOLDER = BENCHMARK_S3_PROJECT_FOLDER

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


def _run_docker_for_scene(
    docker_image_tag: str,
    docker_env_list: list,
    scene: str,
    burst_id: str,
    s3_project_folder: str,
    s3_bucket: str,
    local_outputs_folder: str,
):
    """Utility function to run the docker image for a given scene
    and burst. First, a run will be made to create static layer
    RTC_S1_STATIC products. Second, a run will be made to create
    RTC_S1 backscatter products. The RTC_S1 products are linked to
    the RTC_S1_STATIC products made in the previous run.

    Parameters
    ----------
    docker_image_tag : str
        the docker image tag for sar-pipeline. e.g.
         0.4.1.dev256-g9b7a3f1ea.d20251204
    docker_env_list : list
        A list of environment variables to be passed
        to the container. These should be separated by '-e'. e.g.
        ['-e', 'KEY1=VAL1','-e','KEY2=VAL2','-e', ...]
    scene : str
        The scene to be processed. e.g.
        S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD
    burst_id : Burst id to be processed corresponding to the scene
        e.g. t070_149815_iw3
    s3_project_folder : str
        Project folder for products to be uploaded to.
    s3_bucket : str
        The S3 bucket to upload to.
    local_outputs_folder : str
        Local folder for outputs to be saved.
    """

    logging.info(f"Static layers will be produced and linked to backscatter data.")
    if not Path(local_outputs_folder).exists():
        os.makedirs(local_outputs_folder)
    logging.info(f"Saving test outputs locally to : {local_outputs_folder}")
    logging.info(f"Uploading outputs to : {s3_bucket}/{s3_project_folder}")
    logging.info(
        "Mounting test data directory for results: "
        f"{local_outputs_folder}:/home/rtc_user/working/results",
    )
    logging.info(f"RUN 1: Producing Static Layers (RTC_S1_STATIC)")

    # mount the local directory for results
    volume_mount_list = ["-v", f"{local_outputs_folder}:/home/rtc_user/working/results"]
    # Optional -> mount somewhere to store downloads
    # volume_mount_list += [
    #     "-v",
    #     f"/data/working/downloads:/home/rtc_user/working/downloads",
    # ]
    # Optional -> mount the scratch directory
    # volume_mount_list += ["-v", f"/data/working/scratch:/home/rtc_user/working/scratch"]

    cmd = [
        "docker",
        "run",
        *volume_mount_list,
        "--rm",
        *docker_env_list,
        f"sar-pipeline:{docker_image_tag}",
        "--scene",
        scene,
        "--burst_id_list",
        burst_id,
        "--product",
        "RTC_S1_STATIC",
        "--backscatter_convention",
        "gamma0",
        "--collection_number",
        "1",
        "--s3_bucket",
        s3_bucket,
        "--s3_project_folder",
        s3_project_folder,
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
        *volume_mount_list,
        "--rm",
        *docker_env_list,
        f"sar-pipeline:{docker_image_tag}",
        "--scene",
        scene,
        "--burst_id_list",
        burst_id,
        "--product",
        "RTC_S1",
        "--backscatter_convention",
        "gamma0",
        "--collection_number",
        "1",
        "--s3_bucket",
        s3_bucket,
        "--s3_project_folder",
        s3_project_folder,
        "--link_static_layers",
        "--linked_static_layers_s3_project_folder",
        s3_project_folder,
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


def _compare_product_to_benchmark(
    product: Literal["RTC_S1", "RTC_S1_STATIC"],
    test_product_s3_prefix: str,
    benchmark_product_s3_prefix: str,
    local_comparison_outputs_folder: str,
    s3_bucket: str,
):
    """Utility to Run a comparison between newly made
     test products and the benchmark product

    Parameters
    ----------
    product : Literal["RTC_S1","RTC_S1_STATIC"]
        The type of product being compared
    test_product_s3_prefix : str
        The path to the newly made test product in AWS
    benchmark_product_s3_product : str
        The path to the benchmark product in AWS
    local_comparison_outputs_folder : str
        Where the outputs of the comparison should be stored
    s3_bucket : str
        The S3 bucket containing the products.
    """

    logging.info(
        f"COMPARE 1: Comparing created Static Layers with Existing Benchmark Product"
    )

    logging.info(f"Creating comparison outputs directory :  ")
    os.makedirs(f"{local_comparison_outputs_folder}", exist_ok=True)

    runner = CliRunner()
    args = ["--product", product]
    args += ["--s3-product-folder-1", test_product_s3_prefix]
    args += ["--s3-product-folder-2", benchmark_product_s3_prefix]
    args += ["--s3-bucket", s3_bucket]
    args += ["--out-folder", f"{local_comparison_outputs_folder}"]

    result = runner.invoke(compare_products, args, catch_exceptions=False)
    if result.exception:
        logging.exception(
            "An error occurred during CLI invocation", exc_info=result.exception
        )
        logging.error(result.output)

    assert result.exit_code == 0

    # ensure that the files and tif values have not changed. If so, these are breaking changes to the
    # product, and the persistent comparison products must be updated - see description at top
    file_differences = f"{local_comparison_outputs_folder}/file_differences.json"
    tif_differences = f"{local_comparison_outputs_folder}/tif_differences.json"
    assert not check_files_have_changed(
        file_differences
    ), f"Error, there are breaking changes in the test files compared to the comparison product. \
    Check {file_differences} and update comparison products if needed."
    assert not check_tifs_have_changed(
        tif_differences
    ), f"Error, the created tif values have changed compared to the comparison product. \
    Check {tif_differences} and update comparison products if needed."


@pytest.mark.dependency(name="test_docker_single_pol_scene")
def test_docker_single_pol_scene():
    """Run the docker image and create a burst product for a single pol SLC. First,
    static layers (RTC_S1_STATIC) are created. Then, NRB (RTC_S1) products are created
    that get linked to the previous static layers.
    """
    logging.info(f"Running full process for single pol (HH), this may take a while...")
    _run_docker_for_scene(
        docker_image_tag=DOCKER_TAG,
        docker_env_list=ENV_VARS,
        scene=TEST_1_SCENE,
        burst_id=TEST_1_BURST,
        s3_project_folder=TEST_S3_PROJECT_FOLDER,
        s3_bucket=TEST_S3_BUCKET,
        local_outputs_folder=LOCAL_TEST_OUTPUTS_DIR,
    )


@pytest.mark.dependency(depends=["test_docker_single_pol_scene"])
def test_compare_single_pol_rtc_s1_static_product_to_benchmark():
    """
    This function will compare the static layer outputs (RTC_S1_STATIC) created in the test_docker_single_scene
    function with existing outputs in AWS. The output of this are data that describe
    the differences in product files, metadata (.json and xml) and in the GeoTiffs themselves.
    These outputs can be used to understand if the changes made are planned and acceptable.
    """

    test_product_s3_prefix = (
        f"{TEST_S3_PROJECT_FOLDER}/{TEST_1_RTC_S1_STATIC_PRODUCT_S3_PREFIX}"
    )
    benchmark_product_s3_prefix = TEST_1_BENCHMARK_RTC_S1_STATIC_S3_PRODUCT_FOLDER
    local_comparison_outputs_folder = (
        f"{LOCAL_COMPARISON_OUTPUTS_DIR}/TEST_1_RTC_S1_STATIC"
    )

    _compare_product_to_benchmark(
        product="RTC_S1_STATIC",
        test_product_s3_prefix=test_product_s3_prefix,
        benchmark_product_s3_prefix=benchmark_product_s3_prefix,
        local_comparison_outputs_folder=local_comparison_outputs_folder,
        s3_bucket=TEST_S3_BUCKET,
    )


@pytest.mark.dependency(depends=["test_docker_single_pol_scene"])
def test_compare_single_pol_rtc_s1_product_to_benchmark():
    """
    This function will compare the RTC_S1 outputs created in the test_docker_single_pol_scene
    function with existing outputs in AWS. The output of this are data that describe
    the differences in product files, metadata (.json and xml) and in the GeoTiffs themselves.
    These outputs can be used to understand if the changes made are planned and acceptable.
    """

    test_product_s3_prefix = (
        f"{TEST_S3_PROJECT_FOLDER}/{TEST_1_RTC_S1_PRODUCT_S3_PREFIX}"
    )
    benchmark_product_s3_prefix = TEST_1_BENCHMARK_RTC_S1_S3_PRODUCT_FOLDER
    local_comparison_outputs_folder = f"{LOCAL_COMPARISON_OUTPUTS_DIR}/TEST_1_RTC_S1"

    _compare_product_to_benchmark(
        product="RTC_S1",
        test_product_s3_prefix=test_product_s3_prefix,
        benchmark_product_s3_prefix=benchmark_product_s3_prefix,
        local_comparison_outputs_folder=local_comparison_outputs_folder,
        s3_bucket=TEST_S3_BUCKET,
    )


@pytest.mark.dependency(name="test_docker_dual_pol_scene")
def test_docker_dual_pol_scene():
    """Run the docker image and create a burst product for a dual pol SLC. First,
    static layers (RTC_S1_STATIC) are created. Then, NRB (RTC_S1) products are created
    that get linked to the previous static layers.
    """
    logging.info(f"Running full process for dual pol (VV+VH), this may take a while...")
    _run_docker_for_scene(
        docker_image_tag=DOCKER_TAG,
        docker_env_list=ENV_VARS,
        scene=TEST_2_SCENE,
        burst_id=TEST_2_BURST,
        s3_project_folder=TEST_S3_PROJECT_FOLDER,
        s3_bucket=TEST_S3_BUCKET,
        local_outputs_folder=LOCAL_TEST_OUTPUTS_DIR,
    )


@pytest.mark.dependency(depends=["test_docker_dual_pol_scene"])
def test_compare_dual_pol_rtc_s1_static_product_to_benchmark():
    """
    This function will compare the RTC_S1_STATIC outputs created in the test_docker_dual_pol_scene
    function with existing outputs in AWS. The output of this are data that describe
    the differences in product files, metadata (.json and xml) and in the GeoTiffs themselves.
    These outputs can be used to understand if the changes made are planned and acceptable.
    """

    test_product_s3_prefix = (
        f"{TEST_S3_PROJECT_FOLDER}/{TEST_2_RTC_S1_STATIC_PRODUCT_S3_PREFIX}"
    )
    benchmark_product_s3_prefix = TEST_2_BENCHMARK_RTC_S1_STATIC_S3_PRODUCT_FOLDER
    local_comparison_outputs_folder = (
        f"{LOCAL_COMPARISON_OUTPUTS_DIR}/TEST_2_RTC_S1_STATIC"
    )

    _compare_product_to_benchmark(
        product="RTC_S1_STATIC",
        test_product_s3_prefix=test_product_s3_prefix,
        benchmark_product_s3_prefix=benchmark_product_s3_prefix,
        local_comparison_outputs_folder=local_comparison_outputs_folder,
        s3_bucket=TEST_S3_BUCKET,
    )


@pytest.mark.dependency(depends=["test_docker_dual_pol_scene"])
def test_compare_dual_pol_rtc_s1_product_to_benchmark():
    """
    This function will compare the RTC_S1 outputs created in the test_docker_dual_pol_scene
    function with existing outputs in AWS. The output of this are data that describe
    the differences in product files, metadata (.json and xml) and in the GeoTiffs themselves.
    These outputs can be used to understand if the changes made are planned and acceptable.
    """

    test_product_s3_prefix = (
        f"{TEST_S3_PROJECT_FOLDER}/{TEST_2_RTC_S1_PRODUCT_S3_PREFIX}"
    )
    benchmark_product_s3_prefix = TEST_2_BENCHMARK_RTC_S1_S3_PRODUCT_FOLDER
    local_comparison_outputs_folder = f"{LOCAL_COMPARISON_OUTPUTS_DIR}/TEST_2_RTC_S1"

    _compare_product_to_benchmark(
        product="RTC_S1",
        test_product_s3_prefix=test_product_s3_prefix,
        benchmark_product_s3_prefix=benchmark_product_s3_prefix,
        local_comparison_outputs_folder=local_comparison_outputs_folder,
        s3_bucket=TEST_S3_BUCKET,
    )


TEST_AM_SCENE = False
if TEST_AM_SCENE:

    @pytest.mark.dependency(name="test_docker_antimeridian_scene")
    def test_docker_antimeridian_scene():
        """Run the docker image and create a burst product for a single pol SLC that crosses
        The antimeridian. First, static layers (RTC_S1_STATIC) are created. Then, NRB (RTC_S1)
        products are created that get linked to the previous static layers.
        """
        logging.info(
            f"Running full process for ANTIMERIDIAN single pol (HH), this may take a while..."
        )
        logging.info(f"Static layers will be produced and linked to backscatter data.")
        _run_docker_for_scene(
            docker_image_tag=DOCKER_TAG,
            docker_env_list=ENV_VARS,
            scene=TEST_3_SCENE,
            burst_id=TEST_3_BURST,
            s3_project_folder=TEST_S3_PROJECT_FOLDER,
            s3_bucket=TEST_S3_BUCKET,
            local_outputs_folder=LOCAL_TEST_OUTPUTS_DIR,
        )

    @pytest.mark.dependency(depends=["test_docker_antimeridian_scene"])
    def test_compare_antimeridian_rtc_s1_static_product_to_benchmark():
        """
        This function will compare the RTC_S1_STATIC outputs created in the test_docker_dual_pol_scene
        function with existing outputs in AWS. The output of this are data that describe
        the differences in product files, metadata (.json and xml) and in the GeoTiffs themselves.
        These outputs can be used to understand if the changes made are planned and acceptable.
        """

        test_product_s3_prefix = (
            f"{TEST_S3_PROJECT_FOLDER}/{TEST_3_RTC_S1_STATIC_PRODUCT_S3_PREFIX}"
        )
        benchmark_product_s3_prefix = TEST_3_BENCHMARK_RTC_S1_STATIC_S3_PRODUCT_FOLDER
        local_comparison_outputs_folder = (
            f"{LOCAL_COMPARISON_OUTPUTS_DIR}/TEST_3_RTC_S1_STATIC"
        )

        _compare_product_to_benchmark(
            product="RTC_S1_STATIC",
            test_product_s3_prefix=test_product_s3_prefix,
            benchmark_product_s3_prefix=benchmark_product_s3_prefix,
            local_comparison_outputs_folder=local_comparison_outputs_folder,
            s3_bucket=TEST_S3_BUCKET,
        )

    @pytest.mark.dependency(depends=["test_docker_antimeridian_scene"])
    def test_compare_antimeridian_rtc_s1_product_to_benchmark():
        """
        This function will compare the RTC_S1 outputs created in the test_docker_dual_pol_scene
        function with existing outputs in AWS. The output of this are data that describe
        the differences in product files, metadata (.json and xml) and in the GeoTiffs themselves.
        These outputs can be used to understand if the changes made are planned and acceptable.
        """

        test_product_s3_prefix = (
            f"{TEST_S3_PROJECT_FOLDER}/{TEST_3_RTC_S1_PRODUCT_S3_PREFIX}"
        )
        benchmark_product_s3_prefix = TEST_3_BENCHMARK_RTC_S1_S3_PRODUCT_FOLDER
        local_comparison_outputs_folder = (
            f"{LOCAL_COMPARISON_OUTPUTS_DIR}/TEST_3_RTC_S1"
        )

        _compare_product_to_benchmark(
            product="RTC_S1",
            test_product_s3_prefix=test_product_s3_prefix,
            benchmark_product_s3_prefix=benchmark_product_s3_prefix,
            local_comparison_outputs_folder=local_comparison_outputs_folder,
            s3_bucket=TEST_S3_BUCKET,
        )
