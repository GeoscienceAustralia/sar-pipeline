import click
import logging
from pathlib import Path
from pyroSAR import identify
from pyroSAR.gamma import geocode
from pyroSAR.gamma.dem import dem_import
import shutil
import sys
import tomli

from sar_antarctica.nci.processing.GAMMA.GAMMA_utils import set_gamma_env_variables

logging.basicConfig(
    format="%(asctime)s | %(levelname)s : %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger("gammapy")
log.setLevel(logging.INFO)


@click.command()
@click.argument("workflow_config", nargs=1)
@click.argument("scene_config", nargs=1)
def cli(workflow_config: str, scene_config: str):

    # Read in config file
    with open(workflow_config, "rb") as f:
        workflow_config_dict = tomli.load(f)

    with open(scene_config, "rb") as f:
        scene_config_dict = tomli.load(f)

    # Split config dicts up to ease readability
    config_inputs = scene_config_dict["inputs"]
    config_outputs = scene_config_dict["outputs"]
    config_gamma = workflow_config_dict["gamma"]
    config_geocode = workflow_config_dict["geocode"]

    # Environment variables for GAMMA must be set
    set_gamma_env_variables(
        config_gamma["software_env_var"], config_gamma["libs_env_var"]
    )

    # Identify scene
    scene_zip = Path(config_inputs["scene"])
    scene_id = scene_zip.stem
    log.info(f"Scene ID: {scene_id} has the following metadata:\n{scene_zip}")
    if scene_zip.exists():
        pyrosar_scene_id = identify(scene_zip)

    # Construct output scenes
    data_dir = Path(config_outputs["data"])
    processed_scene_dir = (
        data_dir
        / config_outputs["processed"]
        / pyrosar_scene_id.outname_base(extensions=None)
    )
    pyrosar_temp_dir = (
        data_dir / "temp" / pyrosar_scene_id.outname_base(extensions=None)
    )
    pyrosar_temp_log_dir = pyrosar_temp_dir / "logfiles"

    log.info("creating directories:")
    for dir in [processed_scene_dir, pyrosar_temp_dir, pyrosar_temp_log_dir]:
        dir.mkdir(parents=True, exist_ok=True)
        log.info(f"    {dir}")

    # Copy over orbit file
    orbit_file = Path(config_inputs["orbit"])
    orbit_filename = orbit_file.name
    shutil.copy(orbit_file, pyrosar_temp_dir / orbit_filename)

    # Create DEM in GAMMA format
    dem_tif = Path(config_inputs["dem"])
    dem_gamma = pyrosar_temp_dir / dem_tif.stem

    if dem_gamma.exists():
        log.info("DEM exists")
        pass
    else:
        log.info("running DEM")

        dem_import(
            src=str(dem_tif),
            dst=str(dem_gamma),
            geoid=None,
            logpath=str(pyrosar_temp_log_dir),
            outdir=str(dem_tif.parent),
        )

        log.info("finished DEM")

    # Run geocode process
    # Note that GAMMA geocode from pyrosar produces gamma_0 RTC backscatter
    log.info("running geocode")

    geocode(
        scene=pyrosar_scene_id,
        dem=str(dem_gamma),
        tmpdir=str(pyrosar_temp_dir),
        outdir=str(processed_scene_dir),
        spacing=config_geocode["spacing"],
        scaling=config_geocode["scaling"],
        func_geoback=1,
        nodata=(0, -99),
        update_osv=False,
        osvdir=str(pyrosar_temp_dir),
        allow_RES_OSV=False,
        cleanup=False,
        export_extra=[
            "inc_geo",
            "dem_seg_geo",
            "ls_map_geo",
            "pix_area_gamma0_geo",
            "pix_ratio_geo",
        ],
        basename_extensions=None,
        removeS1BorderNoiseMethod="pyroSAR",
        refine_lut=False,
        rlks=None,
        azlks=None,
        s1_osv_url_option=1,
    )

    log.info("finished geocode")


if __name__ == "__main__":

    cli()
