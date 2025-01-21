from pyroSAR import identify

from sar_antarctica.nci.filesystem import get_orbits_nci

from sar_antarctica.nci.preparation.scenes import (
    find_scene_file_from_id,
    parse_scene_file_sensor,
)
from sar_antarctica.nci.preparation.orbits import find_latest_orbit_for_scene
from sar_antarctica.nci.filesystem import get_orbits_nci, get_dem_nci


def prepare_inputs_for_pyrosar_gamma(scene_name):

    scene_file = find_scene_file_from_id(scene_name)

    # Find orbit
    sensor = parse_scene_file_sensor(scene_name)
    orbit_files = get_orbits_nci("POE", sensor)
    orbit_file = find_latest_orbit_for_scene(scene_name, orbit_files)

    # Build DEM
    scene = identify(str(scene_file))
    scene_bbox = scene.bbox().extent
    scene_bounds = (
        scene_bbox["xmin"],
        scene_bbox["ymin"],
        scene_bbox["xmax"],
        scene_bbox["ymax"],
    )

    dem_file = get_dem_nci(scene_name, scene_bounds)

    return (scene_file, orbit_file, dem_file)
