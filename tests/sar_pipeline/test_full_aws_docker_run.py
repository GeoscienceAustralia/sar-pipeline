"""
Overview:
This is test for a complete build and run of the project docker image
It should be completed prior to every PR and release. A local run is generally
required, given the need for credentials, sufficient CPU, RAM and Disk Memory.
Recommend minimum of 4 CPU and 16 GB RAM.

Steps:
1.  Required environment variables are set.
2.  The docker image for the current state is built and tagged.
3.  The container is run, creating static layers (RTC_S1_STATIC) and uploading them to a
    temporary folder in the AWS `test_s3_bucket` and `test_s3_project_folder` set below
4. The container is run again for the backscatter products (RTC_S1), linking them to the
    RTC_S1_STATIC products made in the above step. The results are similarly uploaded to AWS.
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
import re

logging.basicConfig(
    level=logging.DEBUG,  # or INFO
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)

logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parent.parent

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
                "env.secret was found but some variables are missing. Add the required variables."
            )
        else:
            logging.info("Environment variables loaded from env.secret successfully.")
            ENV_VARS = ["--env-file", f'{PROJECT_ROOT / "env.secret"}']

    except:
        raise FileExistsError(
            "Could not find env.secret file at project root containing required environment variables for run. "
            "Create this file with required variables OR ensure environment is configured correctly "
            "(e.g. when running automated tests on GitHub)"
        )


@pytest.fixture(scope="module", autouse=True)
def build_image():
    docker_tag = re.sub(r"[^a-zA-Z0-9_.-]", "-", sar_pipeline.__version__)
    logging.info(
        f"Building docker image sar-pipeline:{docker_tag} for testing, this may take a few minutes..."
    )
    result = subprocess.run(
        [
            "docker",
            "build",
            "-t",
            f"sar-pipeline:{docker_tag}",
            "-f",
            "Docker/Dockerfile",
            ".",
        ],
        stdout=sys.stdout,
        stderr=sys.stderr,
        text=True,
    )
    assert (
        result.returncode == 0
    ), f"Docker build failed: {result.returncode}\nSTDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"


def test_docker_with_args():
    logging.info(f"Running full process, this may take a while...")
    logging.info(f"Static layers will be produced and linked to backscatter data.")
    run_dt = str(datetime.now()).replace(" ", "_")
    test_name = Path(__file__).stem
    test_s3_bucket = "deant-data-public-dev"
    test_s3_project_folder = f"TMP/sar-pipeline/{run_dt}/{test_name}"
    logging.info(f"Uploading outputs to : {test_s3_bucket}/{test_s3_project_folder}")
    docker_tag = re.sub(r"[^a-zA-Z0-9_.-]", "-", sar_pipeline.__version__)

    logging.info(f"RUN 1: Producing Static Layers")
    logging.info(
        "Mounting test data directory for results: "
        f"{CURRENT_DIR}/data/isce3_rtc/results:/home/rtc_user/working/results",
    )
    cmd = [
        "docker",
        "run",
        "-v",
        f"{CURRENT_DIR}/data/isce3_rtc/results:/home/rtc_user/working/results",
        "--rm",
        *ENV_VARS,
        f"sar-pipeline:{docker_tag}",
        "--scene",
        "S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD",
        "--burst_id_list",
        "t070_149815_iw3",
        "--product",
        "RTC_S1_STATIC",
        "--backscatter_convention",
        "gamma0",
        "--collection_number",
        "1",
        "--s3_bucket",
        test_s3_bucket,
        "--s3_project_folder",
        test_s3_project_folder,
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
        f"{CURRENT_DIR}/data/isce3_rtc/results:/home/rtc_user/working/results",
        "--rm",
        *ENV_VARS,
        f"sar-pipeline:{docker_tag}",
        "--scene",
        "S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD",
        "--burst_id_list",
        "t070_149815_iw3",
        "--product",
        "RTC_S1",
        "--backscatter_convention",
        "gamma0",
        "--collection_number",
        "1",
        "--s3_bucket",
        test_s3_bucket,
        "--s3_project_folder",
        test_s3_project_folder,
        "--link_static_layers",
        "--linked_static_layers_s3_project_folder",
        test_s3_project_folder,
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
