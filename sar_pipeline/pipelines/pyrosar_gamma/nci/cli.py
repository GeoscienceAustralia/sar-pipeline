import click
import datetime
from pathlib import Path, PurePath
import tomli
import logging
from typing import Literal
import rasterio

from sar_pipeline.preparation.nci.scenes import (
    find_scene_file_from_id,
    NCIMissingSceneError,
)
from sar_pipeline.utils.sentinel1 import is_s1_filename, is_s1_id
from sar_pipeline.pipelines.pyrosar_gamma.processing.pyroSAR.pyrosar_geocode import (
    run_pyrosar_gamma_geocode,
)
from sar_pipeline.pipelines.pyrosar_gamma.nci.submission.pyrosar_gamma.submit_job import (
    submit_job,
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


# Set up default configuration for use in CLI
DEFAULT_CONFIGURATION = (
    Path(__file__).resolve().parents[3] / "configs/pyrosar_gamma/s1_rtc.toml"
)


def configure(ctx, param, filename):
    with open(filename, "rb") as f:
        configuration_dictionary = tomli.load(f)
    ctx.default_map = configuration_dictionary


# nci-pyrosar-gamma-rtc-submit-workflow
@click.command()
@click.argument("scene", type=str)
@click.option(
    "-c",
    "--config",
    type=click.Path(dir_okay=False),
    default=DEFAULT_CONFIGURATION,
    callback=configure,
    is_eager=True,
    expose_value=False,
    help="Read option defaults from the specified .toml file",
    show_default=True,
)
@click.option(
    "--spacing",
    type=int,
    required=True,
    help="The target pixel spacing in meters. E.g. 20",
)
@click.option(
    "--scaling",
    type=click.Choice(
        ["linear", "db", "both"],
    ),
    required=True,
    help="The value scaling of the backscatter values; either linear, db, or both",
)
@click.option(
    "--target-crs",
    type=click.Choice(
        ["4326", "3031"],
    ),
    required=True,
    help="The EPSG number for the target coordinate reference system. Only 4326 and 3031 are supported",
)
@click.option(
    "--orbit-dir",
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
    ),
    required=True,
    help="Path to where orbit files are stored on NCI filesystem",
)
@click.option(
    "--orbit-type",
    type=click.Choice(
        ["POE", "RES", "either"],
    ),
    required=True,
    help="The orbit type to use, POE for precise, RES for restitutional, either for the most recent.",
)
@click.option(
    "--etad-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default=None,
    help="Path to where ETAD correction files are stored. If provided, the ETAD correction will be applied.",
)
@click.option(
    "--output-dir",
    type=click.Path(file_okay=False, path_type=Path),
    default="/g/data/yp75/projects/sar-antarctica-processing/pyrosar_gamma/",
    help="Path to where outputs will be stored. Must be an absolute path, relative paths will result in an error.",
)
@click.option(
    "--gamma-lib-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="/g/data/dg9/GAMMA/GAMMA_SOFTWARE-20230712",
    help="Path to GAMMA software binaries.",
)
@click.option(
    "--gamma-env-var",
    type=str,
    default="/g/data/yp75/projects/pyrosar_processing/sar-pyrosar-nci:/apps/fftw3/3.3.10/lib:/apps/gdal/3.6.4/lib64",
    help="Environment variable to point to symlinked .sso objects to ensure GAMMA runs",
)
@click.option("--ncpu", type=str, default="4", help="Number of CPU to request.")
@click.option(
    "--mem", type=str, default="32", help="Amount of memory to request in GB."
)
@click.option("--queue", type=str, default="normal", help="NCI queue to submit to.")
@click.option("--project", type=str, default="u46", help="NCI project to submit to.")
@click.option(
    "--walltime",
    type=str,
    default="02:00:00",
    help="Amount of walltime to request for the job.",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Flag for dry-run. Produces the submission script without launching it.",
)
@click.option(
    "--dotenv-location",
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
    ),
    default=PROJECT_ROOT,
)
def submit_pyrosar_gamma_workflow(
    scene: str,
    spacing: int,
    scaling: Literal["linear", "db", "both"],
    target_crs: Literal["4326", "3031"],
    orbit_dir: Path,
    orbit_type: Literal["POE", "RES", "either"],
    etad_dir: Path | None,
    output_dir: Path,
    gamma_lib_dir: Path,
    gamma_env_var: str,
    ncpu: str,
    mem: str,
    queue: str,
    project: str,
    walltime: str,
    dry_run: bool,
    dotenv_location: Path,
):
    """Submit a job to the NCI job queue to run the pyroSAR+GAMMA workflow to process SCENE with given options."""

    # set NCI required env variables
    REQUIRED_ENV_VARIABLES = [
        "NCI_API_SCENE_FILE_LOCATION",
        "NCI_API_ORBIT_FILE_LOCATION",
        "NCI_FILESYSTEM_FILE_LOCATION",
        "CONDA_EXE",
        "PYGSSEARCH_CONDA_ENV",
    ]

    # Identify and load required environment variables
    identify_and_load_missing_env_vars(REQUIRED_ENV_VARIABLES, dotenv_location)

    if not output_dir.exists():
        click.echo(f"Creating output directory: {output_dir}")
        output_dir.mkdir(parents=True)

    # Function to get scene ids from CLI input
    # This function uses recursion. It begins by checking if the input string is any of
    # A Sentinel-1 ID, filename, or path, before assuming that the user has provided a file
    # containing these items. It will then open the file, and apply the previous checks to
    # the contents line-by-line.
    def _get_nci_s1_scene_id(input: str) -> list[str]:
        input_as_path = Path(input)

        # Check if input string is a Sentinel-1 ID
        if is_s1_id(input):
            click.echo(f"A Sentinel-1 id was passed: {input}, type = {type(input)}")
            return [input]

        # Check if input string is a Sentinel-1 filename
        elif is_s1_filename(input):
            click.echo(f"A Sentinel-1 filename was passed: {input}")
            scene_id = PurePath(input).stem
            return [scene_id]

        # Check if the input string is a file
        elif input_as_path.is_file():
            if input_as_path.suffix == ".zip":
                # Confirm that stem is either a Sentinel-1 SAFE dir or Sentinel-1 ID
                if is_s1_filename(input_as_path.stem) or is_s1_id(input_as_path.stem):
                    click.echo(
                        f"A zipped Sentinel-1 file path was passed: {input_as_path}"
                    )
                    scene_id = input_as_path.stem
                if input_as_path is not None:
                    return [scene_id]

            # Otherwise, open the file and process the content line-by-line, using the same
            # logic above (ID, filename, or path)
            else:
                scene_ids = []
                click.echo("A file was passed, attempting to open and process contents")
                with open(input_as_path) as f:
                    for line in f:
                        line_scene_id = _get_nci_s1_scene_id(line.rstrip())
                        scene_ids.extend(line_scene_id)
                if scene_ids is not None:
                    return scene_ids

        # If unsuccessful, raise an error for the user.
        else:
            raise ValueError(
                "scene must be a valid Sentinel-1 id/zipped file/path, or a file containing valid Sentinel-1 ids/zipped files/paths"
            )

    processing_list = _get_nci_s1_scene_id(scene)
    click.echo(f"Processing list length: {len(processing_list)}")

    pbs_parameters = {
        "ncpu": ncpu,
        "mem": mem,
        "queue": queue,
        "project": project,
        "walltime": walltime,
    }

    log_dir = output_dir / "submission/logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    submitted_scenes = []
    for scene_id in processing_list:

        # Check if already processed
        processed_path = output_dir / f"data/processed_scene/{scene_id}"
        if len(list(processed_path.glob("*gamma0*.tif"))) > 0:
            click.echo(
                f"{scene_id} has already been processed. Check output at {processed_path}"
            )
        else:
            # Find files on NCI
            try:
                scene_file = find_scene_file_from_id(scene_id)
                orbit_file = find_orbit_from_id(scene_id, orbit_type, orbit_dir)

                submit_job(
                    scene=scene_file,
                    spacing=spacing,
                    scaling=scaling,
                    target_crs=target_crs,
                    orbit_file=orbit_file,
                    etad_dir=etad_dir,
                    output_dir=output_dir,
                    log_dir=log_dir,
                    gamma_lib_dir=gamma_lib_dir,
                    gamma_env_var=gamma_env_var,
                    pbs_parameters=pbs_parameters,
                    conda_exe=None,
                    dry_run=dry_run,
                )

                submitted_scenes.append(scene_id)

            except (NCIMissingSceneError, NCIMissingOrbitError) as e:
                continue

    if dry_run == True:
        submitted_scenes_file = f'{output_dir}/unprocessed_scenes_{datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")}.txt'
    else:
        submitted_scenes_file = f'{output_dir}/submitted_scenes_{datetime.datetime.now().strftime("%Y-%m-%d_%H:%M:%S")}.txt'

    click.echo(f"Writing submitted scenes to {submitted_scenes_file}")
    with open(
        submitted_scenes_file,
        "w",
    ) as f:
        for scene in submitted_scenes:
            f.write(f"{scene}\n")
