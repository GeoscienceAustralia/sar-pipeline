import click
from pathlib import Path
from pyroSAR import identify
import rasterio

from sar_antarctica.nci.filesystem import get_orbits_nci

from sar_antarctica.nci.preparation.scenes import (
    find_scene_file_from_id,
    parse_scene_file_sensor,
)
from sar_antarctica.nci.preparation.orbits import find_latest_orbit_for_scene
from sar_antarctica.nci.preparation.dem import get_cop30_dem_for_bounds


def write_file_paths(
    config_file: Path,
    scene_file: Path,
    orbit_file: Path,
    dem_file: Path,
    data_dir: Path,
    ancillary_dir="ancillary",
    processed_dir="processed_scene",
):
    inputs_header = "[inputs]\n"
    scene_setting = f"scene = '{str(scene_file)}'\n"
    orbit_setting = f"orbit = '{str(orbit_file)}'\n"
    dem_setting = f"dem = '{str(dem_file)}'\n"

    outputs_header = "[outputs]\n"
    data_path_setting = f"data = '{str(data_dir)}'\n"
    ancillary_setting = f"ancillary = '{ancillary_dir}'\n"
    processed_setting = f"processed = '{processed_dir}'\n"

    with open(config_file, "w") as cf:
        cf.writelines(
            [
                inputs_header,
                scene_setting,
                orbit_setting,
                dem_setting,
                "\n",
                outputs_header,
                data_path_setting,
                ancillary_setting,
                processed_setting,
            ]
        )


@click.command()
@click.argument("scene_id", nargs=1)
@click.argument("scene_config", nargs=1)
def main(scene_id: str, scene_config: str):
    """Generate a configuration file for a scene ID

    Parameters
    ----------
    scene_id : str
        ID of scene to process
    scene_config : str
        where to store the output configuration file
    """
    print(f"Processing scene: {scene_id} \n")

    # Set the data path for outputs
    data_dir = Path("/g/data/yp75/projects/sar-antractica-processing/data")

    # Path to configuration file for scene
    config_file = Path(scene_config)

    # Identify location of scene on GADI
    scene_file = find_scene_file_from_id(scene_id)

    # Identify location of latest orbit file on GADI
    scene_sensor = parse_scene_file_sensor(scene_id)
    poe_orbits = get_orbits_nci("POE", scene_sensor)
    latest_poe_file = find_latest_orbit_for_scene(scene_id, poe_orbits)

    # Identify bounds of scene and use bounding box to build DEM
    scene = identify(str(scene_file))
    scene_bbox = scene.bbox().extent
    scene_bounds = (
        scene_bbox["xmin"],
        scene_bbox["ymin"],
        scene_bbox["xmax"],
        scene_bbox["ymax"],
    )

    # Set path for dem and create
    dem_dir = data_dir / "dem"
    dem_file = dem_dir / f"{scene_id}_dem.tif"
    _, _ = get_cop30_dem_for_bounds(
        bounds=scene_bounds, save_path=dem_file, ellipsoid_heights=True
    )

    # Write to config file
    write_file_paths(config_file, scene_file, latest_poe_file, dem_file, data_dir)


if __name__ == "__main__":

    main()
