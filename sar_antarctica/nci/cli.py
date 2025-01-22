import click
from pathlib import Path

from sar_antarctica.nci.filesystem import get_orbits_nci
from sar_antarctica.nci.submission.pyrosar_gamma.prepare_input import (
    get_orbit_and_dem,
)
from sar_antarctica.nci.preparation.orbits import (
    filter_orbits_to_cover_time_window,
)
from sar_antarctica.nci.preparation.scenes import (
    parse_scene_file_sensor,
    parse_scene_file_dates,
    find_scene_file_from_id,
)
from sar_antarctica.nci.processing.pyroSAR.pyrosar_geocode import (
    run_pyrosar_gamma_geocode,
)
from sar_antarctica.nci.submission.pyrosar_gamma.submit_job import submit_job

GAMMA_LIBRARY = Path("/g/data/dg9/GAMMA/GAMMA_SOFTWARE-20230712")
GAMMA_ENV = "/g/data/yp75/projects/pyrosar_processing/sar-pyrosar-nci:/apps/fftw3/3.3.10/lib:/apps/gdal/3.6.4/lib64"
OUTPUT_DIR = Path("/g/data/yp75/projects/sar-antractica-processing/pyrosar_gamma/")


@click.command()
@click.argument("scene_name", type=str)
def find_scene_file(scene_name):
    scene_file = find_scene_file_from_id(scene_name)

    click.echo(scene_file)


@click.command()
@click.argument(
    "scene",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.argument("spacing", type=int)
@click.argument("scaling", type=str)
@click.argument("ncpu", type=str)
@click.argument("mem", type=str)
@click.argument("queue", type=str)
@click.argument("project", type=str)
@click.argument("walltime", type=str)
def submit_pyrosar_gamma_workflow(
    scene, spacing, scaling, ncpu, mem, queue, project, walltime
):

    pbs_parameters = {
        "ncpu": ncpu,
        "mem": mem,
        "queue": queue,
        "project": project,
        "walltime": walltime,
    }

    submit_job(scene, spacing, scaling, pbs_parameters)


@click.command()
@click.argument(
    "scene",
    type=click.Path(exists=True, file_okay=True, dir_okay=False, path_type=Path),
)
@click.argument("spacing", type=int)
@click.argument("scaling", type=str)
def run_pyrosar_gamma_workflow(scene, spacing, scaling):

    click.echo("Preparing orbit and DEM")
    orbit, dem = get_orbit_and_dem(scene)

    click.echo(f"    Identified orbit: {orbit}")
    click.echo(f"    Identified DEM: {dem}")

    click.echo("Running processing")
    run_pyrosar_gamma_geocode(
        scene=scene,
        orbit=orbit,
        dem=dem,
        output=OUTPUT_DIR,
        gamma_library=GAMMA_LIBRARY,
        gamma_env=GAMMA_ENV,
        geocode_spacing=spacing,
        geocode_scaling=scaling,
    )


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
