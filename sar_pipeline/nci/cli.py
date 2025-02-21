import click
from pathlib import Path
import tomli
import logging
import subprocess

from sar_pipeline.nci.filesystem import get_orbits_nci
from sar_pipeline.nci.submission.pyrosar_gamma.prepare_input import (
    get_orbit_and_dem,
)
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
from sar_pipeline.nci.upload.push_folder_to_s3 import push_files_in_folder_to_s3

logging.basicConfig(level=logging.INFO)


@click.command()
@click.argument("scene_name", type=str)
def find_scene_file(scene_name):
    scene_file = find_scene_file_from_id(scene_name)

    click.echo(scene_file)


DEFAULT_CONFIGURATION = Path(__file__).resolve().parent / "configs/default.toml"


def configure(ctx, param, filename):
    with open(filename, "rb") as f:
        configuration_dictionary = tomli.load(f)
    ctx.default_map = configuration_dictionary


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
@click.option("--spacing", type=int)
@click.option("--scaling", type=click.Choice(["linear", "db"]))
@click.option("--target-crs", type=click.Choice(["EPSG:4326", "EPSG:3031"]))
@click.option("--ncpu", type=str, default="4")
@click.option("--mem", type=str, default="32")
@click.option("--queue", type=str, default="normal")
@click.option("--project", type=str, default="u46")
@click.option("--walltime", type=str, default="02:00:00")
@click.option(
    "--output-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="/g/data/yp75/projects/sar-antractica-processing/pyrosar_gamma/",
)
def submit_pyrosar_gamma_workflow(
    scene, spacing, scaling, target_crs, ncpu, mem, queue, project, walltime, output_dir
):

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

    submit_job(scene, spacing, scaling, target_crs, pbs_parameters, log_dir)


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
@click.option("--spacing", type=int)
@click.option("--scaling", type=click.Choice(["linear", "db"]))
@click.option("--target-crs", type=click.Choice(["EPSG:4326", "EPSG:3031"]))
@click.option(
    "--orbit-dir", type=click.Path(exists=True, file_okay=False, path_type=Path)
)
@click.option("--orbit-type", type=click.Choice(["POE", "RES", "either"]))
@click.option(
    "--output-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="/g/data/yp75/projects/sar-antractica-processing/pyrosar_gamma/",
)
@click.option(
    "--gamma-lib-dir",
    type=click.Path(exists=True, file_okay=False, path_type=Path),
    default="/g/data/dg9/GAMMA/GAMMA_SOFTWARE-20230712",
)
@click.option(
    "--gamma-env-var",
    type=str,
    default="/g/data/yp75/projects/pyrosar_processing/sar-pyrosar-nci:/apps/fftw3/3.3.10/lib:/apps/gdal/3.6.4/lib64",
)
def run_pyrosar_gamma_workflow(
    scene,
    spacing,
    scaling,
    target_crs,
    orbit_dir,
    orbit_type,
    output_dir,
    gamma_lib_dir,
    gamma_env_var,
):

    click.echo("Preparing orbit and DEM")
    dem_output_dir = output_dir / "data/dem"

    orbit, dem = get_orbit_and_dem(scene, dem_output_dir, orbit_dir, orbit_type)

    click.echo(f"    Identified orbit: {orbit}")
    click.echo(f"    Identified DEM: {dem}")

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
    )

    if target_crs == "EPSG:3031":
        click.echo("Performing reprojection to EPSG:3031")
        # Identify all files containing gamma0-rtc_geo
        files_to_reproject = list(
            processed_scene_directory.glob("*gamma0-rtc_geo*.tif")
        )

        for file in files_to_reproject:
            click.echo(f"    Processing {file.stem}")
            output_file = file.parent / (file.stem + "_3031" + file.suffix)
            cmd = [
                "gdalwarp",
                "-t_srs",
                target_crs,
                "-tr",
                str(spacing),
                str(spacing),  # Set output resolution to target spacing
                "-r",
                "bilinear",  # Use bilinear resampling
                str(file),
                str(output_file),
            ]

            subprocess.run(cmd, check=True)


@click.command()
@click.argument("scene")
def find_orbits_for_scene(scene: str):
    sensor = parse_scene_file_sensor(scene)
    start_time, stop_time = parse_scene_file_dates(scene)

    poe_paths = get_orbits_nci("POE", sensor)
    relevent_poe_paths = filter_orbits_to_cover_time_window(
        poe_paths, start_time, stop_time
    )
    for orbit in relevent_poe_paths:
        print(orbit["orbit"])

    res_paths = get_orbits_nci("RES", sensor)
    relevant_res_paths = filter_orbits_to_cover_time_window(
        res_paths, start_time, stop_time
    )
    for orbit in relevant_res_paths:
        print(orbit["orbit"])


@click.command()
@click.argument("src_folder", type=click.Path(exists=True, file_okay=False))
@click.argument("s3_bucket")
@click.argument("s3_bucket_folder")
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
    push_files_in_folder_to_s3(
        src_folder=src_folder,
        s3_bucket=s3_bucket,
        s3_bucket_folder=s3_bucket_folder,
        upload_folder=upload_folder,
        exclude_extensions=exclude_extensions,
        exclude_files=exclude_files,
        region_name=region_name,
    )
