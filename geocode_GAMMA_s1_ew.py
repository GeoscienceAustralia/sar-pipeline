import asf_search as asf
import os
import tomli
from pyroSAR import identify
from pyroSAR.gamma import geocode
from pyroSAR.gamma.api import diff
from pathlib import Path

import logging
import sys

if __name__ == "__main__":

    logging.basicConfig(
        format="%(asctime)s | %(levelname)s : %(message)s",
        level=logging.INFO,
        stream=sys.stdout,
    )
    log = logging.getLogger("gammapy")
    log.setLevel(logging.INFO)

    REPO_DIR = Path(__file__).resolve().parent
    CONFIG_DIR = REPO_DIR.parent.joinpath("configuration_files")

    config_file = CONFIG_DIR.joinpath("S1A_EW_GRDM_1SDH_20191129T171536_20191129T171618_030128_03713E_7A5A_config.toml")

    with open(config_file, "rb") as f:
        config_dict = tomli.load(f)

    # Set up paths
    DATA_DIR = Path(config_dict["paths"]["data"])
    RESULTS_DIR = DATA_DIR.joinpath("results/gamma")
    TEMP_DIR = DATA_DIR.joinpath("scratch")
    LOG_DIR = TEMP_DIR.joinpath("logs")
    ORBIT_DIR = DATA_DIR.joinpath("orbits")

    # Set up files
    scene_zip = Path(config_dict["scene"])
    orbit_eof = Path(config_dict["orbit"])
    dem_tif = Path(config_dict["dem"])
    dem_gamma = TEMP_DIR.joinpath(f"dem/{dem_tif.stem}")
    dem_gamma_par = dem_gamma.with_suffix('.par')

    # Set up GAMMA and lib
    GAMMA_HOME_PATH = config_dict["gamma"]["path"]
    REQUIRED_LIBS_PATH = config_dict["gamma"]["required_libs"]

    gamma_env_value = os.environ.get("GAMMA_HOME", None)
    ld_lib_env_value = os.environ.get("LD_LIBRARY_PATH", None)

    if gamma_env_value is None:
        os.environ["GAMMA_HOME"] = GAMMA_HOME_PATH
        gamma_env_value = os.environ["GAMMA_HOME"]


    if ld_lib_env_value is None:
        os.environ["LD_LIBRARY_PATH"] = REQUIRED_LIBS_PATH
        ld_lib_env_value = os.environ["LD_LIBRARY_PATH"]

    # get scene metadata
    if scene_zip.exists():
        pyrosar_scene_id = identify(scene_zip)
    else:
        print("Scene not available, download first")

    # DEM creation
    # GAMMA requires specific file formats, and pyroSAR currently provides this
    # through dem_autocreate or dem_import
    # pyroSAR.dem.dem_import currently missing option for nodata
    # return to using diff implementation instead
    if dem_gamma.exists():
        log.info("DEM exists")
        pass
    else:
        # Function
        log.info("running DEM")
        diff.dem_import(
            input_DEM=str(dem_tif), 
            DEM=str(dem_gamma),
            DEM_par=str(dem_gamma_par),
            no_data=-9999,
            geoid="-", 
            logpath=str(LOG_DIR), 
            outdir=str(dem_tif.parent)
        )
        log.info("finished DEM")

    # geocode function
    # Settings
    spacing = 40
    scaling = 'linear' # scale of final product, linear, db
    refarea = 'gamma0' # e.g. gamma0, sigma0, beta0 or ['gamma0','sigma0']
    # Function
    log.info("running geocode")
    geocode(
        scene=pyrosar_scene_id, 
        dem=str(dem_gamma), 
        tmpdir=str(TEMP_DIR),
        outdir=str(RESULTS_DIR), 
        spacing=spacing, 
        scaling=scaling, 
        func_geoback=1,
        nodata=(0, -99), 
        update_osv=True, 
        osvdir=str(ORBIT_DIR), 
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