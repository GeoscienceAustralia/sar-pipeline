import click
from pathlib import Path

from sar_antarctica.nci.preparation.scenes import find_scene_file_from_id
from sar_antarctica.nci.preparation.orbits import find_latest_orbit_for_scene




def write_pyrosar_settings(config_file: Path):
    with open(config_file, "a") as cf:
        header = "[geocode]\n"
        spacing_setting = "spacing = 40\n"
        scaling_setting = "scaling = 'linear'\n"

        cf.writelines([header, spacing_setting, scaling_setting, "\n"])


def write_gamma_settings(config_file: Path):
    with open(config_file, "a") as cf:
        header = "[gamma]\n"
        software_setting = "software_env_var = '/g/data/dg9/GAMMA/GAMMA_SOFTWARE-20230712'\n"
        libs_setting = "libs_env_var = '/g/data/yp75/projects/pyrosar_processing/sar-pyrosar-nci:/apps/fftw3/3.3.10/lib:/apps/gdal/3.6.4/lib64'\n"

        cf.writelines([header, software_setting, libs_setting, "\n"])

def write_file_paths(config_file: Path, scene_path, orbit_path):
    header = "[files]\n"
    scene_setting = f"scene = '{str(scene_path)}'\n"
    orbit_setting = f"orbit = '{str(orbit_path)}'\n"
    with open(config_file, "a") as cf:
        cf.writelines([header, scene_setting, orbit_setting, "\n"])
        
@click.command()
@click.argument("scene_id")
def main(scene_id: str):
    print(f"Processing scene: {scene_id} \n")

    config_path = Path("/g/data/yp75/ca6983/repositories/sar-antarctica/sar_antarctica/nci/processing/configs")
    config_file = config_path / f"{scene_id}.toml"

    write_gamma_settings(config_file)


    # Identify location of scene on GADI
    scene_path = find_scene_file_from_id(scene_id)
    print(scene_path)

    # Identify location of relevant orbit file on GADI
    latest_poe_file = find_latest_orbit_for_scene(scene_id, orbit_type="POE")
    print(latest_poe_file)

    # Identify location of DEM/process DEM

    write_file_paths(config_file, scene_path, latest_poe_file)

    write_pyrosar_settings(config_file)

if __name__ == "__main__":

    main()