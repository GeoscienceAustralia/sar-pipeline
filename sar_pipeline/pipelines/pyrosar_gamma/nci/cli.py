import click
import datetime
from pathlib import Path, PurePath
import tomli
import logging
from typing import Literal
import rasterio

from sar_pipeline.preparation.nci.scenes import (
    find_scene_file_from_id,
)
from sar_pipeline.utils.environment_variables import identify_and_load_missing_env_vars

logging.basicConfig(level=logging.INFO)

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parents[3]


# find_scene_file
@click.command()
@click.argument("scene", type=str)
@click.option(
    "--dotenv-location",
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
    ),
    default=PROJECT_ROOT,
)
def find_scene_file(scene, dotenv_location):
    """This will identify the path to a given SCENE on the NCI"""

    # Identify and load required environment variables
    identify_and_load_missing_env_vars(REQUIRED_ENV_VARIABLES, dotenv_location)

    scene_file = find_scene_file_from_id(scene)

    click.echo(scene_file)
