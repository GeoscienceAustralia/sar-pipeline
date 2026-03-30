"""
Overview:
This is test for a complete build and run of the project docker image for pyroSAR-GAMMA pipeline.
It is designed to be run in the CI pipeline, but can also be run locally.
The test runs the full workflow for creating static layers and backscatter products for three different scenes,
(TODO) and compares the outputs to benchmark products stored in S3.

The test is run for three scene
- Dual pole HH+HV Sentinel-1 EW SLC (S1A_EW_GRDM_1SDH_20250303T112244_20250303T112308_058139_072E6F_DB7E) scene over Antarctica

Test steps:
1.  A .env file in the project root is required. The file could be created by copying the .env.example file and filling in the required values.
2.  The docker image for the current state is built and tagged.
3.  The container is run, creating static layers (RTC_S1_STATIC) and uploading them to a
    temporary folder in the AWS `TEST_S3_BUCKET` and `TEST_S3_PROJECT_FOLDER` set below.
4. The newly created products are compared to benchmark products stored at the
    BENCHMARK_S3_PROJECT_FOLDER to understand any differences that have been introduced (e.g.
    breaking differences in Geotiff data and changes in metadata).

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
import shutil

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

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parents[2]

TEST_SCENE = "S1A_EW_GRDM_1SDH_20250303T112244_20250303T112308_058139_072E6F_DB7E"


@pytest.fixture(scope="module", autouse=True)
def build_image():
    """build and tag the docker image for the current codebase to be used in tests"""
    logging.info(
        f"Building docker image sar-pipeline for testing, this may take a few minutes..."
    )

    if os.path.exists(PROJECT_ROOT / "sar-processing"):
        subprocess.run(
            ["sudo", "chmod", "-R", "777", PROJECT_ROOT / "sar-processing"],
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True,
        )
        shutil.rmtree(PROJECT_ROOT / "sar-processing")

    result = subprocess.run(
        [
            "docker",
            "build",
            "-t",
            "sar-pipeline",
            "-f",
            "Docker/pyrosar_gamma/Dockerfile",
            ".",
        ],
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True,
    )
    assert (
        result.returncode == 0
    ), f"Docker build failed: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"

    yield  # Run the tests

    if os.path.exists(PROJECT_ROOT / "sar-processing"):
        subprocess.run(
            ["sudo", "chmod", "-R", "777", PROJECT_ROOT / "sar-processing"],
            stdout=sys.stdout,
            stderr=sys.stderr,
            text=True,
        )
        shutil.rmtree(PROJECT_ROOT / "sar-processing")


def _run_docker_for_scene(
    scene: str,
):
    """Utility function to run the docker image for a given scene
    and burst.

    Parameters
    ----------
    scene : str
        The scene to be processed.
    """
    cmd = [
        "docker",
        "run",
        "-v",
        f"{PROJECT_ROOT}/.env:/app/.env",
        "-v",
        f"{PROJECT_ROOT}/sar-processing:/app/sar-processing",
        "-v",
        "/usr/local/GAMMA_SOFTWARE-20230712:/usr/local/GAMMA_SOFTWARE-20230712",
        "sar-pipeline",
        "--scene",
        scene,
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


# TODO We need to compare the products withen the benchmark products and update the benchmark products on S3 after we implemented the code to upload results..
@pytest.mark.dependency(name="test_docker_dual_pol_scene")
def test_docker_dual_pol_scene():
    """Run the docker image and create a product for a dual pol SLC."""

    logging.info(f"Running full process for dual pol (HH+HV), this may take a while...")
    _run_docker_for_scene(scene=TEST_SCENE)
