import click
from pathlib import Path

from sar_antarctica.nci.preparation.scenes import find_scene_file_from_id
from sar_antarctica.nci.preparation.orbits import find_latest_orbit_for_scene

def write_file_paths(config_file: Path, scene_path, orbit_path, dem_path, data_path, ancillary_dir="ancillary", processed_dir="processed_scene"):
    inputs_header = "[inputs]\n"
    scene_setting = f"scene = '{str(scene_path)}'\n"
    orbit_setting = f"orbit = '{str(orbit_path)}'\n"
    dem_setting = f"dem = '{str(dem_path)}'\n"

    outputs_header = "[outputs]\n"
    data_path_setting = f"data = '{str(data_path)}'\n"
    ancillary_setting = f"ancillary = '{ancillary_dir}'\n"
    processed_setting = f"processed = '{processed_dir}'\n"

    with open(config_file, "w") as cf:
        cf.writelines([
            inputs_header, 
            scene_setting, 
            orbit_setting,
            dem_setting, 
            "\n", 
            outputs_header, 
            data_path_setting,
            ancillary_setting,
            processed_setting
        ])
        
@click.command()
@click.argument("scene_id", nargs=1)
@click.argument('scene_config', nargs=1)
def main(scene_id: str, scene_config: str):
    print(f"Processing scene: {scene_id} \n")

    # config_path = Path("/g/data/yp75/projects/sar-antractica-processing/config/scene_config")
    config_file = Path(scene_config)

    # Identify location of scene on GADI
    scene_path = find_scene_file_from_id(scene_id)

    # Identify location of relevant orbit file on GADI
    latest_poe_file = find_latest_orbit_for_scene(scene_id, orbit_type="POE")



    # Identify location of DEM/process DEM
    dem_file = f"{scene_id}_dem.tif"
    dem_path = Path("/g/data/yp75/projects/pyrosar_processing/data/dem") / dem_file

    # Set the data path for outputs
    data_path = Path("/g/data/yp75/projects/sar-antractica-processing/data")

    # Write to config file
    write_file_paths(
        config_file, 
        scene_path, 
        latest_poe_file, 
        dem_path, 
        data_path
    )

if __name__ == "__main__":

    main()