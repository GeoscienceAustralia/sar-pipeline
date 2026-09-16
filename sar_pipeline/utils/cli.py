import click
import logging
from pathlib import Path

from sar_pipeline.utils.bursts import find_burst_ids_for_scene

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--scene",
    required=True,
    type=str,
    help="Scene to get the list of bursts ids for. "
    "e.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD",
)
@click.option(
    "--save-geometries",
    required=False,
    default=None,
    type=click.Path(file_okay=False, path_type=Path),
    help="Folder to save the geometries to as a geojson. "
    "Useful for visualisation of burst locations. Path will be "
    "{save_geometries}/{scene}_burst_geoms.json",
)
def get_burst_ids_for_scene(
    scene,
    save_geometries,
):

    find_burst_ids_for_scene(scene, save_geometries)
