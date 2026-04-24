import docker
from concurrent.futures import ThreadPoolExecutor
from dotenv import load_dotenv
import os
from datetime import datetime
from pathlib import Path
import pandas as pd
import logging
import click
from sar_pipeline.utils.aws import (
    is_sso_session_expired,
    retrieve_aws_secrets,
    sso_login,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parents[3]

DOTENV_PATH = PROJECT_ROOT / ".env"
DOCKERFILE_DIR = PROJECT_ROOT / "Docker/pyrosar_gamma"

dotenv_status = load_dotenv(DOTENV_PATH)
if not dotenv_status:
    raise FileNotFoundError(
        f".env file not found at {DOTENV_PATH}. Please create one with the necessary environment variables."
    )

REQUIRED_ENV_VARIABLES = [
    "EARTHDATA_LOGIN",
    "EARTHDATA_PASSWORD",
    "AWS_DEFAULT_REGION",
    "CDSE_LOGIN",
    "CDSE_PASSWORD",
    "AUS_COP_HUB_LOGIN",
    "AUS_COP_HUB_PASSWORD",
    "AUS_COP_HUB_CLIENT_ID",
    "AUS_COP_HUB_CLIENT_SECRET",
]
env_vars = {var: os.getenv(var) for var in REQUIRED_ENV_VARIABLES}


def run_docker_container(
    scene,
    s3_bucket,
    s3_project_folder,
    processed_scene_tracking_file_s3_folder,
    make_existing_products,
    image_name,
    aws_profile,
    start_time,
) -> tuple[str, int]:

    container_env_vars = env_vars.copy()
    if not is_sso_session_expired():
        secrets = retrieve_aws_secrets(aws_profile=aws_profile)
        if secrets is None:
            logger.error(
                f"{scene}: AWS SSO session has expired and credentials could not be retrieved. Please re-authenticate using 'aws sso login'."
            )
            return scene, -1
        container_env_vars.update(secrets)
        logger.info(
            f"{scene}: Credentials for AWS profile '{aws_profile}' retrieved successfully."
        )
    else:
        logger.error(
            f"{scene}: AWS SSO session has expired. Please re-authenticate using 'aws sso login'."
        )
        return scene, -1

    container_logs_file = f"Container_logs/{start_time}/{scene.replace('/', '_')}.log"

    client = docker.from_env()
    try:
        command = [
            "--scene",
            scene,
            "--s3-bucket",
            s3_bucket,
            "--s3-project-folder",
            s3_project_folder,
            "--processed-scene-tracking-file-s3-folder",
            processed_scene_tracking_file_s3_folder,
            "--make-existing-products",
            str(make_existing_products).lower(),
        ]

        container = client.containers.run(
            image=image_name,
            command=command,
            volumes=[
                "/usr/local/GAMMA_SOFTWARE-20230712:/usr/local/GAMMA_SOFTWARE-20230712",
                f"{str(PROJECT_ROOT)}/sar-processing:/app/sar-processing",
            ],
            environment=container_env_vars,
            detach=True,
            auto_remove=True,
        )
        logger.info(f"{scene}: Started container {container.id} for image {image_name}")
        with open(container_logs_file, "wb") as log_file:
            for line in container.logs(stream=True, follow=True):
                log_file.write(line)
        status = container.wait()
        client.close()
        return scene, status["StatusCode"]
    except Exception as e:
        logger.error(f"{scene}: Error running container for scene {scene}: {e}")
        client.close()
        return scene, -1


@click.command()
@click.option(
    "--scenes-csv",
    required=True,
    help="Path to the CSV file containing the list of scenes to process.",
)
@click.option(
    "--s3-bucket",
    required=False,
    default="dea-public-data-dev",
    type=str,
    help="The bucket to upload the files",
)
@click.option(
    "--s3-project-folder",
    required=False,
    default="experimental/baseline",
    type=str,
    help="The folder within the bucket to upload the files. Note the "
    "final path follows the pattern in the description of this function.",
)
@click.option(
    "--processed-scene-tracking-file-s3-folder",
    required=False,
    default="projects/s1_nrb/monitoring",
    type=str,
    help="The folder within the project’s S3 folder structure to upload the processed scene tracking file. "
    "final path will : {processed_scene_tracking_file_s3_folder}/{acquisition_mode}/processed_scenes ",
)
@click.option(
    "--image-name",
    required=False,
    default="sar-pipeline:latest",
    help="Name of the Docker image to use for processing.",
)
@click.option(
    "--make-existing-products",
    required=False,
    is_flag=True,
    default=False,
    help="Create the product even if it already exists in the desired s3 bucket path. "
    "WARNING - setting this argument may result in duplicate files.",
)
@click.option(
    "--max-workers", default=10, help="Maximum number of parallel workers to run."
)
@click.option(
    "--aws-profile", default="default", help="AWS profile to use for authentication."
)
def run_jobs(
    scenes_csv,
    s3_bucket,
    s3_project_folder,
    processed_scene_tracking_file_s3_folder,
    make_existing_products,
    image_name,
    max_workers,
    aws_profile,
):

    if is_sso_session_expired():
        sso_login(aws_profile=aws_profile)

    image_checking_client = docker.from_env()
    try:
        image_checking_client.images.get(image_name)
        logger.info(f"Docker image '{image_name}' found locally.")
        image_checking_client.close()
    except docker.errors.ImageNotFound:
        logger.error(
            f"Docker image '{image_name}' not found locally. Trying to build it from the Dockerfile."
        )
        try:
            _, build_logs = image_checking_client.images.build(
                path=DOCKERFILE_DIR, tag=image_name, rm=True
            )
            for line in build_logs:
                if "stream" in line:
                    logger.info(line["stream"].strip())
            logger.info(f"Docker image '{image_name}' built successfully.")
            image_checking_client.close()
        except Exception as e:
            logger.error(f"Error building Docker image '{image_name}': {e}")
            return
    except Exception as e:
        logger.error(f"Error checking for Docker image '{image_name}': {e}")
        return

    logger.info(f"Starting parallel processing with image: {image_name}")
    logger.info(f"Scenes CSV: {scenes_csv}")
    logger.info(f"S3 bucket: {s3_bucket}")
    logger.info(f"S3 project folder: {s3_project_folder}")
    logger.info(
        f"Processed scene tracking file S3 folder: {processed_scene_tracking_file_s3_folder}"
    )
    logger.info(f"Make existing products: {make_existing_products}")
    logger.info(f"Maximum workers: {max_workers}")

    start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("Job started at: " + start_time)

    os.makedirs(f"Container_logs/{start_time}", exist_ok=True)
    logger.info(f"Container logs will be saved to: Container_logs/{start_time}/")

    success = []
    failed = []

    scenes_df = pd.read_csv(scenes_csv)
    scenes = scenes_df["scene"].tolist()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = [
            executor.submit(
                run_docker_container,
                scene,
                s3_bucket,
                s3_project_folder,
                processed_scene_tracking_file_s3_folder,
                make_existing_products,
                image_name,
                aws_profile,
                start_time,
            )
            for scene in scenes
        ]

        for future in futures:
            result = future.result()
            if result:
                name, code = result
                if code == 0:
                    success.append(name)
                    status = "SUCCESS"
                    logger.info(f"Job for scene {name} completed successfully.")
                else:
                    failed.append(name)
                    status = "FAILED"
                    logger.error(
                        f"Job for scene {name} failed with status code {code}."
                    )
                logger.info(f"Scene: {name}, Status: {status}")

    end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    logger.info("Job ended at: " + end_time)

    logger.info(f"Total scenes processed: {len(scenes)}")
    logger.info(f"Successful scenes: {len(success)}")
    logger.info(f"Failed scenes: {len(failed)}")
    logger.info(f"Successfully processed scenes: {success}")
    logger.info(f"Failed scenes: {failed}")
