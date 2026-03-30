import click
import logging
from pathlib import Path
import shapely
import rasterio

from sar_pipeline.preparation.downloads.scenes import (
    download_scene_from_preference_list_with_timeout,
    query_scene_from_cdse,
    query_scene_from_asf,
    VALID_SCENE_DATA_SOURCES,
    NonSingleSceneResultError,
)
from sar_pipeline.preparation.downloads.orbits import (
    download_orbits_from_preference_list,
    VALID_ORBIT_DATA_SOURCES,
)
from sar_pipeline.pipelines.pyrosar_gamma.processing.pyroSAR.pyrosar_geocode import (
    run_pyrosar_gamma_geocode,
)

from sar_pipeline.utils.environment_variables import identify_and_load_missing_env_vars

from sar_pipeline.utils.general import log_timing
from sar_pipeline.utils.antimeridian import (
    check_shape_crosses_antimeridian,
    get_bounds_for_antimeridian_shape,
)
from sar_pipeline.utils.dem import get_best_dem_type_for_scene, VALID_DEMS
from dem_handler.dem.cop_glo30 import get_cop30_dem_for_bounds
from dem_handler.dem.rema import get_rema_dem_for_bounds

from sar_pipeline.utils.post_processing import (
    gdal_reproject,
    gdal_update_nodata,
    gdal_add_overviews,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

CURRENT_DIR = Path(__file__).parent.resolve()
PROJECT_ROOT = CURRENT_DIR.parents[3]


@click.command()
@click.option(
    "--scene",
    type=str,
    required=True,
    help="scene id. E.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD",
)
@click.option(
    "--dem-type",
    required=True,
    default="best",
    type=str,
    help="The type of DEM that should be downloaded for processing the scene. "
    "If 'best' is provided, logic will be used to select the most appropriate DEM out of the REMA_32 and cop_glo30. "
    "Ellipsoidal height values will be used where no DEM data exists (e.g. over water)"
    f"Values must be one of {VALID_DEMS}",
)
@click.option(
    "--download-folder",
    required=False,
    default=Path("sar-processing/downloads"),
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder where downloaded files should go",
)
@click.option(
    "--out-folder",
    required=False,
    default=Path("sar-processing/s1_rtc"),
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder where final products will be written",
)
@click.option(
    "--scene-data-source",
    required=False,
    default="AUS_COP_HUB ASF CDSE",
    type=str,
    help="Where to download the scene from. "
    "Can be passed as a string or list of preferences separated by a space. "
    "If the scene cannot be found at the first preference, the next will be used. "
    "E.g. `--scene-data-source 'AUS_COP_HUB CDSE'` will first try to download the scene from "
    "The Copernicus Australasia Regional Data Hub before moving to try from the European CDSE. "
    "Credentials for the desired data source must be set as environment variables."
    f"Values must be one of {VALID_SCENE_DATA_SOURCES} passed as a space separated string. E.g. `--scene-data-source 'AUS_COP_HUB ASF CDSE'`",
)
@click.option(
    "--orbit-data-source",
    required=False,
    default="ASF CDSE",
    type=str,
    help="Where to download the orbit files from. "
    "Can be passed as a string or list of preferences separated by a space. "
    "If the orbits files cannot be found at the first preference, the next will be used. "
    "E.g. `--orbit-data-source 'CDSE ASF'` will first try to download the orbit files from "
    "The CDSE before moving to try from the ASF. "
    "Credentials for the desired data source must be set as environment variables."
    f"Values must be one of {VALID_ORBIT_DATA_SOURCES} passed as a space separated string. E.g. `--orbit-data-source 'CDSE ASF'`",
)
@click.option(
    "--gamma-library",
    required=False,
    type=click.Path(file_okay=False, path_type=Path),
    default=Path("/usr/local/GAMMA_SOFTWARE-20230712"),
    help="Path to the gamma library for processing",
)
@click.option(
    "--gamma-env",
    required=False,
    type=str,
    default=f"{PROJECT_ROOT}/.pixi/envs/default/lib:{Path.home()}/gamma_symlinks",
    help="Name of the gamma environment for processing. This should be set up with the gamma library specified by --gamma-library",
)
@click.option(
    "--geocode-spacing",
    required=False,
    type=int,
    default=20,
    help="The geocoding grid spacing in meters. Default is 20m.",
)
@click.option(
    "--geocode-scaling",
    required=False,
    type=str,
    default="both",
    help="The scaling convention for the geocoded output. Default is 'both', which rescales the values using linear and decibel scaling.",
)
@click.option(
    "etad",
    "--etad",
    required=False,
    type=click.Path(exists=True, file_okay=True, path_type=Path),
    help="Path to the ETAD file to use for processing."
    "If not provided, the workflow will attempt to download an ETAD file from the CDSE for the scene date."
    "If no ETAD file can be found, processing will continue without an ETAD file.",
)
@click.option("--make-folders", required=False, default=True, help="Create folders")
@click.option(
    "--dotenv-location",
    type=click.Path(
        exists=True,
        file_okay=False,
        path_type=Path,
    ),
    default=PROJECT_ROOT,
)
@click.option(
    "--target-crs",
    type=click.Choice(
        ["4326", "3031"],
    ),
    required=False,
    default="3031",
    help="The EPSG number for the target coordinate reference system. Only 4326 and 3031 are supported",
)
@log_timing
def run_pyrosar_gamma_workflow(
    scene,
    dem_type,
    download_folder,
    out_folder,
    scene_data_source,
    orbit_data_source,
    gamma_library,
    gamma_env,
    geocode_spacing,
    geocode_scaling,
    etad,
    make_folders,
    dotenv_location,
    target_crs,
) -> None:
    """
    Retrieve all required inputs for RTC_S1, including scene data, orbit files,
    DEMs, and passes the collected inputs to the processing function.
    The function determines the appropriate DEM, handles anti‑meridian geometry,
    validates and downloads scene and orbit data from preferred sources.
    It then passes the collected inputs to the pyrosar gamma RTC processing function, along with necessary parameters such as geocoding spacing and scaling.
    The function also logs key steps and decisions throughout the process, such as data sources used.

    Returns None. The final geocoded products are written to the specified output folder.
    """
 
    # set required env variables
    REQUIRED_ENV_VARIABLES = [
        "EARTHDATA_LOGIN",
        "EARTHDATA_PASSWORD",
        "AWS_ACCESS_KEY_ID",
        "AWS_SECRET_ACCESS_KEY",
        "CDSE_LOGIN",
        "CDSE_PASSWORD",
        "AUS_COP_HUB_LOGIN",
        "AUS_COP_HUB_PASSWORD",
        "AUS_COP_HUB_CLIENT_ID",
        "AUS_COP_HUB_CLIENT_SECRET",
    ]

    # Identify and load required environment variables
    identify_and_load_missing_env_vars(REQUIRED_ENV_VARIABLES, dotenv_location)

    logger.info(f"Downloading data for scene : {scene}")
    logger.info(f"Data source for scene download : {scene_data_source}")
    logger.info(f"Data source for orbit download : {orbit_data_source}")

    # sub-folders for downloads
    orbit_folder = download_folder / "orbits"
    scene_folder = download_folder / "scenes"

    if make_folders:
        logger.info(f"Making output folders if not existing")
        download_folder.mkdir(parents=True, exist_ok=True)
        orbit_folder.mkdir(parents=True, exist_ok=True)
        scene_folder.mkdir(parents=True, exist_ok=True)
        out_folder.mkdir(parents=True, exist_ok=True)

    # get the dem_type
    if dem_type not in VALID_DEMS:
        raise ValueError(
            f"Invalid --dem_type {dem_type}. --dem-type valid values are {VALID_DEMS}"
        )

    # get the preference list scene data sources
    scene_data_sources = scene_data_source.split(" ")
    if not all([ds in VALID_SCENE_DATA_SOURCES for ds in scene_data_sources]):
        raise ValueError(
            f"--scene-data-source valid values are {VALID_SCENE_DATA_SOURCES}"
        )
    logger.info(
        f"The order of preference for platform used to download the scene is : {scene_data_sources}"
    )

    # get the preference of orbit file data sources
    orbit_data_sources = orbit_data_source.split(" ")
    if not all([ds in VALID_ORBIT_DATA_SOURCES for ds in orbit_data_sources]):
        raise ValueError(
            f"--orbit-data-source valid values are {VALID_ORBIT_DATA_SOURCES}"
        )
    logger.info(
        f"The order of preference for platform used to download the orbits is : {orbit_data_sources}"
    )

    try:
        # Query the CDSE to make sure the scene exists
        logger.info(f"Searching CDSE for scene metadata : {scene}")
        scene_results, metadata_src = query_scene_from_cdse(scene), "CDSE"
    except Exception as e:
        # Fallback to ASF
        logger.error(f"CDSE Query failed. Error : {e}")
        logger.info(f"Falling back to ASF search for scene metadata : {scene}")
        logger.warning(f"ASF may not have the most recent data available from the CDSE")
        scene_results, metadata_src = query_scene_from_asf(scene), "ASF"

    if len(scene_results) != 1:
        raise NonSingleSceneResultError(
            f"Expected 1 scene, found {len(scene_results)} results for scene id : {scene}. Check input scene."
        )
    else:
        logger.info(f"Scene metadata successfully retrieved from {metadata_src}")
        scene_metadata = scene_results[0]
        if metadata_src == "CDSE":
            scene_polygon = shapely.geometry.shape(scene_metadata["GeoFootprint"])
        if metadata_src == "ASF":
            scene_polygon = shapely.geometry.shape(scene_metadata.geometry)
        # show the original scene shape and bounds
        logger.info(f"The original scene shape is : {scene_polygon}")
        logger.info(f"The original scene bounds are : {scene_polygon.bounds}")

    # check if the scene crosses the antimeridian
    scene_crosses_antimeridian = check_shape_crosses_antimeridian(scene_polygon)
    if scene_crosses_antimeridian:
        logger.warning(
            f"The scene crosses the antimeridian. scene : {scene}, original shape : {scene_polygon}"
        )
        # use the full scene bounds for an antimeridian scene
        scene_bounds = get_bounds_for_antimeridian_shape(scene_polygon)
        logger.info(
            f"Getting the corrected scene bounds crossing the antimeridian : {scene_bounds}"
        )
    else:
        scene_bounds = scene_polygon.bounds

    # get the best dem for processing if required
    if dem_type == "best":
        logger.info("Finding the best DEM for processing the scene")
        dem_type = get_best_dem_type_for_scene(scene_bounds)
    logger.info(f"The dem_type: {dem_type} will be used to process scene: {scene}")

    # iterate through the preferences for the scene data source and download the scene
    SCENE_PATH, scene_polygon, _ = download_scene_from_preference_list_with_timeout(
        timeout_mins=60,
        early_exit_code=102,
        scene_data_source_preferences=scene_data_sources,
        scene=scene,
        download_folder=scene_folder,
        unzip=True,
    )

    # # download the orbits
    logger.info(f"Downloading Orbits for scene : {scene}")
    ORBIT_PATH = download_orbits_from_preference_list(
        scene_safe_file=scene + ".SAFE",
        download_folder=orbit_folder,
        orbit_data_source_preferences=orbit_data_sources,
    )
    logger.info(f"File downloaded to : {ORBIT_PATH}")

    # download the DEM
    dem_folder = download_folder / "dem" / dem_type
    DEM_PATH = dem_folder / f"{scene}_dem.tif"
    if make_folders:
        dem_folder.mkdir(parents=True, exist_ok=True)

    logger.info(
        "Downloading DEM Using the bounds for complete scene over the antimeridian."
    )
    dem_bounds = scene_bounds

    logger.info(f"Downloading DEM type `{dem_type}` to path : {DEM_PATH}")
    if dem_type == "cop_glo30":
        get_cop30_dem_for_bounds(
            bounds=dem_bounds,
            save_path=DEM_PATH,
            ellipsoid_heights=True,
            adjust_at_high_lat=True,
            buffer_pixels=None,
            buffer_degrees=0.3,
            cop30_folder_path=dem_folder,
            geoid_tif_path=dem_folder / f"{scene}_geoid.tif",
            download_dem_tiles=True,
            download_geoid=True,
        )
    elif dem_type in ["REMA_32", "REMA_10", "REMA_2"]:
        dem_resolution = int(dem_type.split("_")[1])
        get_rema_dem_for_bounds(
            bounds=dem_bounds,
            bounds_src_crs=4326,
            save_path=DEM_PATH,
            resolution=dem_resolution,
            buffer_pixels=500,
            ellipsoid_heights=True,
            download_geoid=True,
            geoid_tif_path=dem_folder / f"{scene}_geoid.tif",
            download_dir=dem_folder,
        )
    else:
        raise ValueError(f"dem_type must be one of {VALID_DEMS}")

    processed_scene_directory = run_pyrosar_gamma_geocode(
        scene=SCENE_PATH.resolve(),
        orbit=ORBIT_PATH.resolve(),
        dem=DEM_PATH.resolve(),
        output=out_folder.resolve(),
        gamma_library=gamma_library,
        gamma_env=gamma_env,
        geocode_spacing=geocode_spacing,
        geocode_scaling=geocode_scaling,
        etad=etad,
    )

    # Check file projection and compare to target projection
    output_geocoded_tif_files = list(processed_scene_directory.glob("*_geo*.tif"))

    output_geocoded_crs_values = []
    for tif_file in output_geocoded_tif_files:
        with rasterio.open(tif_file) as src:
            output_geocoded_crs_values.append(src.crs.to_epsg())

    unique_crs_values = list(set(output_geocoded_crs_values))

    if len(unique_crs_values) == 1:
        file_crs = str(unique_crs_values[0])
    else:
        raise ValueError(
            f"Geocoded outputs have more than one CRS value. Values are {unique_crs_values}. Check the geocoding process."
        )

    # If check if files have the target crs, and reproject if not
    if file_crs == target_crs:
        click.echo("Output files are already in target projection.")
        # Add a suffix to the file to make it very clear what projection files are in
        for file in output_geocoded_tif_files:
            updated_path = file.with_stem(file.stem + f"_{file_crs}")
            file.replace(updated_path)
    else:
        click.echo(f"Performing reprojection to EPSG:{target_crs}")
        for file in output_geocoded_tif_files:
            output_file = file.parent / (file.stem + f"_{target_crs}" + file.suffix)

            gdal_reproject(
                src_file=file,
                dst_file=output_file,
                dst_epsg=int(target_crs),
                dst_resolution=geocode_spacing,
                resample_algorithm="bilinear",
            )

            # also update original geocoded files to make the source crs explicit
            updated_path = file.with_stem(file.stem + f"_{file_crs}")
            file.replace(updated_path)

    # For all geocoded files, update all no-data values to nan and add overviews
    # Glob needs to be run again to pick up any scenes that have been reprojected
    files_to_update = list(processed_scene_directory.glob("*_geo*.tif"))

    for file in files_to_update:
        click.echo(f"{file}: Setting nodata to nan and adding overviews")
        # update nodata - overwrite original file
        gdal_update_nodata(file, file, "nan")

        # add overviews - done inplace
        gdal_add_overviews(file)

    return None
