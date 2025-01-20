import click

from sar_antarctica.nci.filesystem import get_orbits_nci
from sar_antarctica.nci.preparation.orbits import (
    filter_orbits_to_cover_time_window,
)
from sar_antarctica.nci.preparation.scenes import (
    parse_scene_file_sensor,
    parse_scene_file_dates,
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
