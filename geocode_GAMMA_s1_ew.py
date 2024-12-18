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

    with open(REPO_DIR.joinpath("config.toml"), "rb") as f:
        config_dict = tomli.load(f)
        
    PROJ_DIR = REPO_DIR.parent
    DATA_DIR = PROJ_DIR.joinpath("data")
    SCENE_DIR = DATA_DIR.joinpath("scenes")
    RESULTS_DIR = DATA_DIR.joinpath("results/gamma")
    DEM_DIR = DATA_DIR.joinpath("dem")
    TEMP_DIR = DATA_DIR.joinpath("scratch")
    LOG_DIR = TEMP_DIR.joinpath("logs")
    ORBIT_DIR = DATA_DIR.joinpath("orbits")

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

    # Set scene variables
    SCENE_ID = config_dict["scene"]

    scene_zip = SCENE_DIR.joinpath(f"{SCENE_ID}.zip")
    dem = DEM_DIR.joinpath(f"{SCENE_ID}_dem")
    dem_src = DEM_DIR.joinpath(f"{SCENE_ID}_dem.tif")
    dem_gamma = DEM_DIR.joinpath(f"{SCENE_ID}_dem.par")

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
            input_DEM=str(dem_src), 
            DEM=str(dem),
            DEM_par=str(dem_gamma),
            no_data=-9999,
            geoid="-", 
            logpath=str(LOG_DIR), 
            outdir=str(DEM_DIR)
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
        dem=str(dem), 
        tmpdir=str(TEMP_DIR),
        outdir=str(RESULTS_DIR), 
        spacing=spacing, 
        scaling=scaling, 
        func_geoback=1,
        nodata=(0, -99), 
        update_osv=True, 
        osvdir=ORBIT_DIR, 
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