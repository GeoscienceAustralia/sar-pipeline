import docker
from concurrent.futures import ThreadPoolExecutor, as_completed
from dotenv import load_dotenv
import os
from datetime import datetime
from pathlib import Path
import pandas as pd
import logging
import click
import shutil
from subprocess import run
from sar_pipeline.utils.general import log_timing
import backoff

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parents[3]

DOTENV_PATH = PROJECT_ROOT / ".env"
DOCKERFILE_DIR = PROJECT_ROOT / "Docker/pyrosar_gamma"

LOCAL_PROCESSING_DIR = PROJECT_ROOT / "sar-processing"

LOCAL_DEM_DIR = LOCAL_PROCESSING_DIR / "downloads/dem/REMA_32"
LOCAL_ORBITS_DIR = LOCAL_PROCESSING_DIR / "downloads/orbits"
LOCAL_SCENES_DIR = LOCAL_PROCESSING_DIR / "downloads/scenes"

LOCAL_PROCESSED_SCENES_DIR = LOCAL_PROCESSING_DIR / "s1_rtc/data/processed_scene"
LOCAL_FINAL_PRODUCTS_DIR = LOCAL_PROCESSING_DIR / "s1_rtc/data/final_product"
LOCAL_TEMP_DIR = LOCAL_PROCESSING_DIR / "s1_rtc/data/temp"

LOCAL_INTERMEDIATE_LIST = [
    LOCAL_DEM_DIR,
    LOCAL_ORBITS_DIR,
    LOCAL_SCENES_DIR,
]

LOCAL_PRODUCT_LIST = [
    LOCAL_PROCESSED_SCENES_DIR,
    LOCAL_FINAL_PRODUCTS_DIR,
]

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
    "AWS_REGION",
    "AWS_ACCESS_KEY_ID",
    "AWS_SECRET_ACCESS_KEY",
    "AWS_SESSION_TOKEN",
]
env_vars = {var: os.getenv(var) for var in REQUIRED_ENV_VARIABLES}
assert all(env_vars.values()), "One or more required environment variables are missing."

DOCKER_CLIENT = docker.from_env(timeout=600)


@backoff.on_exception(
    backoff.expo,
    Exception,
    max_tries=3,
)
def clean_up_dir(dir: Path, pattern: str, force_permissions: bool = False) -> bool:
    """
    Clean up files and directories in the specified directory matching the given pattern.

    Args:
        dir (Path): The directory to clean up.
        pattern (str): The pattern to match files and directories.
        force_permissions (bool): If True, change permissions to allow deletion.
    """
    if force_permissions:
        run(["sudo", "chmod", "-R", "777", dir], check=True)
    objects = list(dir.glob(pattern=pattern))
    if len(objects) == 0:
        logger.info(f"No objects found in {dir} to clean up.")
        return False
    for object in objects:
        if object.is_file():
            object.unlink()
        if object.is_dir():
            shutil.rmtree(object)
    logger.info(
        f"Cleaned up {len(objects)} objects in {dir} matching pattern {pattern}."
    )
    return True


def run_docker_container(
    scene: str,
    s3_bucket: str,
    s3_project_folder: str,
    processed_scene_tracking_file_s3_folder: str,
    make_existing_products: bool,
    image_name: str,
    start_time: str,
    clear_intermediate_files: bool,
    delete_local_outputs: bool,
    timeout: int,
) -> tuple[str, int]:

    container_logs_file = f"Container_logs/{start_time}/{scene.replace('/', '_')}.log"

    container = None
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

        container = DOCKER_CLIENT.containers.run(
            image=image_name,
            command=command,
            volumes=[
                "/usr/local/GAMMA_SOFTWARE-20230712:/usr/local/GAMMA_SOFTWARE-20230712",
                f"{LOCAL_PROCESSING_DIR}:/app/sar-processing",
            ],
            environment=env_vars,
            detach=True,
            auto_remove=False,
        )
        logger.info(f"{scene}: Started container {container.id} for image {image_name}")
        with open(container_logs_file, "wb") as log_file:
            for line in container.logs(stream=True, follow=True):
                log_file.write(line)
        status = container.wait(timeout=timeout)
        if status["StatusCode"] == 0:
            logger.info(f"{scene}: Container for scene {scene} completed successfully.")

            pattern = scene + "*"
            splits = scene.split("_")
            temp_pattern = splits[0] + "*" + splits[1] + "*" + splits[4]

            if clear_intermediate_files:
                for intermediate_dir in LOCAL_INTERMEDIATE_LIST:
                    clean_up_dir(intermediate_dir, pattern, force_permissions=True)
                logger.info(
                    f"{scene}: Cleared intermediate files/folders for scene {scene}."
                )

            if delete_local_outputs:
                for product_dir in LOCAL_PRODUCT_LIST:
                    clean_up_dir(product_dir, pattern, force_permissions=True)

                clean_up_dir(LOCAL_TEMP_DIR, temp_pattern, force_permissions=True)
                logger.info(
                    f"{scene}: Deleted local output files/folders for scene {scene}."
                )

        return scene, status["StatusCode"]
    except Exception as e:
        logger.error(f"{scene}: Error running container for scene {scene}: {e}")
        return scene, -1
    finally:
        if container is not None:
            try:
                container.remove(force=True)
                logger.info(f"{scene}: Container {container.id} removed successfully.")
            except Exception as e:
                logger.error(f"{scene}: Error removing container {container.id}: {e}")


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
    help="The folder within the project's S3 folder structure to upload the processed scene tracking file. "
    "final path will : {processed_scene_tracking_file_s3_folder}/{acquisition_mode}/processed_scenes ",
)
@click.option(
    "--image-name",
    required=False,
    default="sar-pipeline-pyrosar-gamma:latest",
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
    "--clear-intermediate-files",
    is_flag=True,
    default=True,
    help="Clear intermediate files after processing each scene.",
)
@click.option(
    "--delete-local-outputs",
    is_flag=True,
    default=True,
    help="Delete local output files after processing each scene.",
)
@click.option(
    "--general-log-file",
    default="",
    type=str,
    help="Path to the general log file.",
)
@click.option(
    "--container-timeout",
    default="3600",
    type=str,
    help="Timeout for the Docker container in seconds.",
)
@log_timing
def run_jobs(
    scenes_csv,
    s3_bucket,
    s3_project_folder,
    processed_scene_tracking_file_s3_folder,
    make_existing_products,
    image_name,
    max_workers,
    clear_intermediate_files,
    delete_local_outputs,
    general_log_file,
    container_timeout,
):

    if general_log_file != "":
        os.makedirs(os.path.dirname(general_log_file), exist_ok=True)
        file_handler = logging.FileHandler(general_log_file)
        file_handler.setLevel(logging.INFO)
        formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)

    start_time = datetime.now()
    logger.info("Job started at: " + start_time.strftime("%Y-%m-%d %H-%M-%S"))

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
                path=str(DOCKERFILE_DIR), tag=image_name, rm=True
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

    os.makedirs(
        f"Container_logs/{start_time.strftime('%Y-%m-%d_%H-%M-%S')}", exist_ok=True
    )
    logger.info(
        f"Container logs will be saved to: Container_logs/{start_time.strftime('%Y-%m-%d_%H-%M-%S')}/"
    )

    success = []
    failed = []

    scenes_df = pd.read_csv(scenes_csv)
    scenes = scenes_df["scene"].tolist()

    try:
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
                    start_time.strftime("%Y-%m-%d_%H-%M-%S"),
                    clear_intermediate_files,
                    delete_local_outputs,
                    int(container_timeout),
                )
                for scene in scenes
            ]

            for future in as_completed(futures):
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

        end_time = datetime.now()
        logger.info("Job ended at: " + end_time.strftime("%Y-%m-%d %H-%M-%S"))

        logger.info(f"Total processing time: {str(end_time - start_time)}")

        logger.info(f"Total scenes processed: {len(scenes)}")
        logger.info(f"Successful scenes: {len(success)}")
        logger.info(f"Failed scenes: {len(failed)}")
        logger.info(f"Successfully processed scenes: {success}")
        logger.info(f"Failed scenes: {failed}")
    except Exception as e:
        logger.error(f"Error during parallel execution: {e}")
    finally:
        DOCKER_CLIENT.close()
