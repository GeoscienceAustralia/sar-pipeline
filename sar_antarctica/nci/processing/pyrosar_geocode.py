import click
import logging
from pathlib import Path
from pyroSAR import identify
from pyroSAR.gamma import geocode
from pyroSAR.gamma.api import diff
import sys
import tomli

from GAMMA_utils import set_gamma_env_variables

@click.command()
@click.argument("config_toml")
def cli(config_toml: str):
    
    # Read in config file
    with open(config_toml, "rb") as f:
        config_dict = tomli.load(f)    

    # Split config dicts up to ease readability
    config_gamma = config_dict["gamma"]
    config_paths = config_dict["paths"]
    config_files = config_dict["files"]
    config_geocode = config_dict["geocode"]

    # Environment variables for GAMMA must be set
    set_gamma_env_variables(
        config_gamma["software_env_var"], 
        config_gamma["libs_env_var"]
    )

    # Identify scene
    scene_zip = Path(config_paths["scene"]) / config_files["scene"]
    print(scene_zip)
    if scene_zip.exists():
        pyrosar_scene_id = identify(scene_zip)

    # Create DEM in GAMMA format
    dem_tif = Path(config_paths["dem"]) / config_files["dem"]
    dem_gamma = Path(config_paths["temp"]) / dem_tif.stem
    dem_gamma_par = dem_gamma.with_suffix('.par')

    if dem_gamma.exists():
        log.info("DEM exists")
        pass
    else:
        log.info("running DEM")

        diff.dem_import(
            input_DEM=str(dem_tif), 
            DEM=str(dem_gamma),
            DEM_par=str(dem_gamma_par),
            no_data=-9999,
            geoid="-", 
            logpath=config_paths["log"], 
            outdir=str(dem_tif.parent)
        )

        log.info("finished DEM")

    # Run geocode process
    # Note that GAMMA geocode from pyrosar produces gamma_0 RTC backscatter
    log.info("running geocode")

    geocode(
        scene=pyrosar_scene_id, 
        dem=str(dem_gamma), 
        tmpdir=config_paths["temp"],
        outdir=config_paths["results"], 
        spacing=config_geocode["spacing"], 
        scaling=config_geocode["scaling"], 
        func_geoback=1,
        nodata=(0, -99), 
        update_osv=False, 
        osvdir=config_paths["orbit"], 
        allow_RES_OSV=False,
        cleanup=False, 
        export_extra=['inc_geo','dem_seg_geo','ls_map_geo','pix_area_gamma0_geo','pix_ratio_geo'], 
        basename_extensions=None,
        removeS1BorderNoiseMethod='pyroSAR', 
        refine_lut=False, 
        rlks=None, 
        azlks=None,
        s1_osv_url_option=1
    )

    log.info("finished geocode")

if __name__ == "__main__":

    logging.basicConfig(
        format="%(asctime)s | %(levelname)s : %(message)s",
        level=logging.INFO,
        stream=sys.stdout,
    )
    log = logging.getLogger("gammapy")
    log.setLevel(logging.INFO)

    cli()