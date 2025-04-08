import click
from pathlib import Path
import tomli
import logging
import subprocess
from typing import Literal

from sar_pipeline.nci.filesystem import get_orbits_nci
from sar_pipeline.nci.submission.pyrosar_gamma.prepare_input import (
    get_orbit_and_dem,
)
from sar_pipeline.preparation.etad import find_etad_for_scene
from sar_pipeline.nci.preparation.orbits import (
    filter_orbits_to_cover_time_window,
)
from sar_pipeline.nci.preparation.scenes import (
    parse_scene_file_sensor,
    parse_scene_file_dates,
    find_scene_file_from_id,
)
from sar_pipeline.nci.processing.pyroSAR.pyrosar_geocode import (
    run_pyrosar_gamma_geocode,
)
from sar_pipeline.nci.submission.pyrosar_gamma.submit_job import submit_job
from sar_pipeline.utils.s3upload import push_files_in_folder_to_s3
from sar_pipeline.utils.post_processing import (
    gdal_reproject,
    gdal_update_nodata,
    gdal_add_overviews,
)

logging.basicConfig(level=logging.INFO)


# find_scene_file
@click.command()
@click.argument("scene", type=str)
def find_scene_file(scene):
    """This will identify the path to a given SCENE on the NCI"""
    scene_file = find_scene_file_from_id(scene)

    click.echo(scene_file)


# Set up default configuration for use in CLI
DEFAULT_CONFIGURATION = Path(__file__).resolve().parent / "configs/default.toml"


def configure(ctx, param, filename):
    with open(filename, "rb") as f:
        configuration_dictionary = tomli.load(f)
    ctx.default_map = configuration_dictionary


# submit-pyrosar-gamma-workflow
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
    help="Path to where orbit files are stored",
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
    default="/g/data/yp75/projects/sar-antractica-processing/pyrosar_gamma/",
    help="Path to where outputs will be stored.",
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
):
    """Submit a job to the NCI job queue to run the pyroSAR+GAMMA workflow to process SCENE with given options."""

    if not output_dir.exists():
        click.echo(f"Creating output directory: {output_dir}")
        output_dir.mkdir(parents=True)

    scene_file = Path(scene)

    if not scene_file.is_file():
        click.echo("An ID was passed -- locating scene on NCI")
        scene_file = find_scene_file_from_id(scene)

    click.echo(f"Submitting job for scene ID: {scene_file.stem}")

    pbs_parameters = {
        "ncpu": ncpu,
        "mem": mem,
        "queue": queue,
        "project": project,
        "walltime": walltime,
    }

    log_dir = output_dir / "submission/logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    submit_job(
        scene=scene_file,
        spacing=spacing,
        scaling=scaling,
        target_crs=target_crs,
        orbit_dir=orbit_dir,
        orbit_type=orbit_type,
        etad_dir=etad_dir,
        output_dir=output_dir,
        log_dir=log_dir,
        gamma_lib_dir=gamma_lib_dir,
        gamma_env_var=gamma_env_var,
        pbs_parameters=pbs_parameters,
        dry_run=dry_run,
    )


# run_pyrosar_gamma_workflow
@click.command()
@click.argument(
    "scene",
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
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
    help="Path to where orbit files are stored",
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
    default="/g/data/yp75/projects/sar-antractica-processing/pyrosar_gamma/",
    help="Path to where outputs will be stored.",
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
def run_pyrosar_gamma_workflow(
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
):
    """Run the pyroSAR+GAMMA workflow to process SCENE with given options."""

    click.echo("Preparing orbit and DEM")
    dem_output_dir = output_dir / "data/dem"

    orbit, dem = get_orbit_and_dem(scene, dem_output_dir, orbit_dir, orbit_type)

    click.echo(f"    Identified orbit: {orbit}")
    click.echo(f"    Identified DEM: {dem}")

    if etad_dir is not None:
        etad = find_etad_for_scene(str(scene), etad_dir)
        click.echo(f"    Identified ETAD: {etad}")
    else:
        etad = None

    click.echo("Running processing")
    click.echo(f"    Scene: {scene}")
    click.echo(f"    Spacing: {spacing}")
    click.echo(f"    Scaling: {scaling}")
    click.echo(f"    Output directory: {output_dir}")
    click.echo(f"    GAMMA directory: {gamma_lib_dir}")
    click.echo(f"    LD_LIBRARY_PATH (used by GAMMA): {gamma_env_var}")
    processed_scene_directory = run_pyrosar_gamma_geocode(
        scene=scene,
        orbit=orbit,
        dem=dem,
        output=output_dir,
        gamma_library=gamma_lib_dir,
        gamma_env=gamma_env_var,
        geocode_spacing=spacing,
        geocode_scaling=scaling,
        etad=etad,
    )

    # Identify all geocoded data laygers
    files_to_reproject = list(processed_scene_directory.glob("_geo.tif"))
    for file in files_to_reproject:
        click.echo(f"Post-processing {file.stem}")

        if target_crs == "3031":
            click.echo("Performing reprojection to EPSG:3031")
            output_file = file.parent / (file.stem + "_3031" + file.suffix)

            gdal_reproject(
                src_file=file,
                dst_file=output_file,
                dst_epsg=3031,
                dst_resolution=spacing,
                resample_algorithm="bilinear",
            )

            # update nodata
            gdal_update_nodata(output_file, output_file, "nan")

            # add overviews
            gdal_add_overviews(output_file)


# find_orbits_for_scene
@click.command()
@click.argument("scene", type=str)
def find_orbits_for_scene(scene):
    """For a given SCENE, find paths to POE and RES orbits"""
    sensor = parse_scene_file_sensor(scene)
    start_time, stop_time = parse_scene_file_dates(scene)

    poe_paths = get_orbits_nci("POE", sensor)
    relevent_poe_paths = filter_orbits_to_cover_time_window(
        poe_paths, start_time, stop_time
    )
    for orbit in relevent_poe_paths:
        click.echo(f"POE Orbit: {orbit['orbit']}")

    res_paths = get_orbits_nci("RES", sensor)
    relevant_res_paths = filter_orbits_to_cover_time_window(
        res_paths, start_time, stop_time
    )
    for orbit in relevant_res_paths:
        click.echo(f"RES Orbit: {orbit['orbit']}")


# upload_files_in_folder_to_s3
@click.command()
@click.argument("src_folder", type=click.Path(exists=True, file_okay=False))
@click.argument("s3_bucket", type=str)
@click.argument("s3_bucket_folder", type=str)
@click.option(
    "--upload-folder",
    default=False,
    is_flag=True,
    help="Upload the whole folder to specified s3_bucket_folder.",
)
@click.option(
    "--exclude-extensions",
    "-e",
    multiple=True,
    help="File extensions to exclude, e.g., '.txt', '.log'",
)
@click.option(
    "--exclude-files",
    "-f",
    multiple=True,
    help="Specific files to exclude, e.g., 'config.json'",
)
@click.option(
    "--region-name", default="ap-southeast-2", show_default=True, help="AWS region name"
)
def upload_files_in_folder_to_s3(
    src_folder: str,
    s3_bucket: str,
    s3_bucket_folder: str,
    upload_folder: bool,
    exclude_extensions: list[str] = [],
    exclude_files: list[str] = [],
    region_name: str = "ap-southeast-2",
):
    """Upload contents of SRC_FOLDER to S3_BUCKET with prefix S3_BUCKET_FOLDER"""
    push_files_in_folder_to_s3(
        src_folder=src_folder,
        s3_bucket=s3_bucket,
        s3_bucket_folder=s3_bucket_folder,
        upload_folder=upload_folder,
        exclude_extensions=exclude_extensions,
        exclude_files=exclude_files,
        region_name=region_name,
    )
