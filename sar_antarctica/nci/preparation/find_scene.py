import click
from pathlib import Path

from sar_antarctica.nci.preparation.scenes import find_scene_file_from_id
from sar_antarctica.nci.preparation.orbits import find_latest_orbit_for_scene

@click.command()
@click.argument("scene_id")
def main(scene_id: str):
    print(f"Processing scene: {scene_id} \n")

    # Identify location of scene on GADI
    scene_path = find_scene_file_from_id(scene_id)
    print(scene_path)

    # Identify location of relevant orbit file on GADI
    latest_poe_file = find_latest_orbit_for_scene(scene_id, poe_only=True)
    print(latest_poe_file)

    # Identify location of DEM/process DEM

if __name__ == "__main__":

    main()