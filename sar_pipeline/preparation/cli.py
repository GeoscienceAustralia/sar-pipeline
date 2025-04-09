import click
from pathlib import Path

from sar_pipeline.preparation.etad import (
    download_etad_for_scene_from_cdse,
)


@click.command()
@click.argument("scene", type=str)
@click.option(
    "--etad-directory",
    required=True,
    type=click.Path(dir_okay=True, file_okay=False, path_type=Path),
    help="The local directory in which to store the downloaded ETAD file.",
)
@click.option(
    "--cdse-username",
    required=True,
    type=str,
    help="CDSE username (typically an email)",
)
@click.option("--cdse-password", required=True, type=str, help="CDSE password")
@click.option(
    "--unzip/--zip",
    default=False,
    help="Flag indicating whether the downloaded ETAD file should be unzipped "
    "or left zipped. The file is left zipped by default",
)
def download_etad(scene, etad_directory, cdse_username, cdse_password, unzip):
    """This will download an ETAD correction file for a given SCENE from
    the Copernicus Data Space Ecosystem (CDSE)"""
    _ = download_etad_for_scene_from_cdse(
        scene, etad_directory, cdse_username, cdse_password, unzip
    )
