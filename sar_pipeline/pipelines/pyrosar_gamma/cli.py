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
from sar_pipeline.pipelines.pyrosar_gamma.pyrosar_geocode import (
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

from sar_pipeline.pipelines.pyrosar_gamma.metadata.stac import GammaNRBtoSTAC
from sar_pipeline.utils.aws import find_s3_filepaths_from_suffixes, S3Util
from sar_pipeline.utils.checksum import PackageChecksum

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
    default="AUS_COP_HUB ASF CDSE",
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
    default=40,
    help="The geocoding grid spacing in meters. Default is 40m.",
)
@click.option(
    "--geocode-scaling",
    required=False,
    type=click.Choice(
        ["linear", "db", "both"],
    ),
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
    help="Location of the environment file (.env). Assumed to be the project root directory if not provided.",
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
    orbit_folder = download_folder / "orbits" / scene
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
    else:
        click.echo(f"Performing reprojection to EPSG:{target_crs}")
        for file in output_geocoded_tif_files:
            gdal_reproject(
                src_file=file,
                dst_file=file,
                dst_epsg=int(target_crs),
                dst_resolution=geocode_spacing,
                resample_algorithm="bilinear",
            )

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


@click.command()
@click.option(
    "--scene",
    type=str,
    required=True,
    help="scene id. E.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD",
)
@click.option(
    "--results-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder containing the product outputs from pyrosar-GAMMA.",
)
@click.option(
    "--orbit-source-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder containing the orbit source information.",
)
@click.option(
    "--backscatter-convention",
    required=False,
    default="gamma0",
    type=click.Choice(["gamma0", "sigma0", "beta0"]),
    help="Backscatter convention of the product to be made (gamma0, sigma0 or beta0)",
)
@click.option(
    "--collection-number",
    required=False,
    default=1,
    type=int,
    help="The collection number of the product.",
)
@click.option(
    "--s3-bucket",
    required=False,
    default="dea-public-data-dev",
    type=str,
    help="The bucket to upload the files",
)
@click.option(
    "--s3-project-folder",
    required=False,
    default="experimental/baseline",
    type=click.Path(file_okay=False, path_type=Path),
    help="The folder within the bucket to upload the files. Note the "
    "final path follows the pattern in the description of this function.",
)
@click.option(
    "--skip-upload-to-s3",
    required=False,
    is_flag=True,
    default=False,
    help="If we should upload outputs to S3.",
)
@click.option(
    "--make-existing-products",
    required=False,
    is_flag=True,
    default=False,
    help="Create the product even if it already exists in the desired s3 bucket path. "
    "WARNING - setting this argument may result in duplicate files.",
)
@click.option(
    "--validate-stac",
    required=False,
    is_flag=True,
    default=True,
    help="Whether to validate the stac document within the code. "
    "If the stac is not valid, an error is raised and the products "
    "will not be uploaded.",
)
@click.option(
    "--skip-upload-processed-scene-tracking-file",
    required=False,
    is_flag=True,
    default=False,
    help="Whether to skip uploading a json with very basic information"
    "That can be used to track which scenes have been processed. "
    "By default, it will be uploaded to the folder described by"
    "--processed-scene-tracking-file-s3-folder",
)
@click.option(
    "--product-version",
    required=False,
    default="1-0-0",
    type=str,
    help="The version of the product.",
)
@click.option(
    "--processed-scene-tracking-file-s3-folder",
    required=False,
    default="projects/s1_nrb/monitoring",
    type=click.Path(file_okay=False, path_type=Path),
    help="The folder within the project’s S3 folder structure to upload the processed scene tracking file. "
    "final path will : {processed_scene_tracking_file_s3_folder}/{acquisition_mode}/processed_scenes ",
)
@log_timing
def make_metadata_and_upload_product(
    results_folder,
    scene,
    backscatter_convention,
    collection_number,
    s3_bucket,
    s3_project_folder,
    skip_upload_to_s3,
    make_existing_products,
    validate_stac,
    skip_upload_processed_scene_tracking_file,
    product_version,
    orbit_source_folder,
    processed_scene_tracking_file_s3_folder,
):
    """
    Generate STAC metadata for pyroSAR-GAMMA products, reorganise and standardise product filenames,
    build supporting metadata files (STAC JSON, checksums), and optionally upload each product set to an S3 bucket
    following the `GAMMA_RTC_S1_S3_PREFIX_FORMAT` format in `odc.py`.
    The function converts metadata into STAC items, applies optional geometry updates using valid-data masks,
    creates linked assets and metadata references, validates STAC documents if requested, computes checksums,
    and handles overwrite rules for pre‑existing S3 content. It also maintains a processed‑scene tracking record and,
    unless disabled, uploads this summary to a monitoring location within the project’s S3 folder structure.
    """

    # Checking and reading the orbit source folder
    if not orbit_source_folder.is_dir():
        logger.error(f"Orbit source folder does not exist: {orbit_source_folder}")
        raise FileNotFoundError(
            f"Orbit source folder does not exist: {orbit_source_folder}"
        )
    else:
        orbit_source_files = list(Path(orbit_source_folder).glob("*"))
        assert (
            len(orbit_source_files) == 1
        ), f"Expected exactly one file in the orbit source folder, found {len(orbit_source_files)}: {orbit_source_files}"
        orbit_source_file = orbit_source_files[0]
        if "POEORB" in orbit_source_file.name:
            logger.info(
                f"Using precise orbit ephemeris data from file: {orbit_source_file}"
            )
            orbit_source = "POE precise orbit"
        elif "RESORB" in orbit_source_file.name:
            logger.info(
                f"Using restituted orbit ephemeris data from file: {orbit_source_file}"
            )
            orbit_source = "RES restituted orbit"
        else:
            raise ValueError(
                f"Orbit source file name does not contain expected keywords (POEORB or RESORB). "
                f"Please verify that the correct file is being used: {orbit_source_file}"
            )
        logger.info(f"Orbit source information loaded from {orbit_source_file}")

    # tracking file for processed scenes to assist with completion checking
    processed_scene_json = {"scene_id": scene, "stac": []}

    # initialise the S3 utility
    if not skip_upload_to_s3:
        S3UPLOADER = S3Util()

    logger.info(
        f"Making STAC metadata for {results_folder} and uploading to S3 bucket : {s3_bucket} if not already exist or --make-existing-products is set."
    )

    logger.info(
        f"Renaming all files so 'v' is not in the product version number, version is '-' separated, and the platform name is lowercase (e.g s1a)."
    )
    for product_file in results_folder.iterdir():
        if product_file.is_file():
            name = re.sub(
                r"S1[A-Z]",
                lambda m: f"ga_{m.group(0).lower()}_nrb_{product_version}",
                product_file.name,
            )
            new_path = product_file.with_name(name)
            if new_path != product_file:
                logger.info(f"Renaming: {product_file.name} -> {new_path.name}")
                product_file.rename(new_path)

    stac_object = GammaNRBtoSTAC(
        scene_id=scene,
        product_folder=results_folder,
        backscatter_convention=backscatter_convention,
        collection_number=collection_number,
        s3_bucket=s3_bucket,
        orbit_source=orbit_source,
        s3_project_folder=s3_project_folder,
    )

    stac_object.make_stac_item()
    stac_object.add_properties()
    stac_object.rename_asset_files()
    stac_object.add_assets()

    output_file_prefix = stac_object.get_output_filename_prefix()
    stac_filepath = results_folder / f"{output_file_prefix}_stac-item.json"

    stac_object.add_metadata_links(stac_filepath)
    stac_object.add_collection_link()

    stac_object.save(stac_filepath)

    # create a placeholder checksum file to link in stac metadata
    checksum_filepath = results_folder / f"{output_file_prefix}_checksum.sha1"
    Path(checksum_filepath).touch()

    if validate_stac:
        logger.info("Validating STAC document")
        try:
            stac_object.item.validate()
            logger.info("STAC is valid.")
        except Exception as e:
            logger.error(
                f"STAC validation failed, correct error or run without --validate-stac flag.\n{e}"
            )
            raise
    else:
        logger.warning(
            "STAC document is not being validated. set --validate-stac if required."
        )

    # replace the empty checksum file now all required files have been created
    logger.info("Running checksums on product files")
    product_checksum = PackageChecksum()
    checksum_files = [f for f in results_folder.iterdir() if "checksum" not in str(f)]
    product_checksum.add_files(checksum_files)
    product_checksum.write(checksum_filepath.resolve())

    # push folder to S3
    if skip_upload_to_s3:
        logger.info(f"Skipping upload to S3.")
    else:
        # re-check that the files don't already exist in S3. This will help protect against
        # simultaneous runs of the same product. E.g. the product did not exist at the
        # start of the run and was created by another process during this runtime
        logger.info(
            f"Checking if product already exist before uploading files for product : {stac_object.scene_id}"
        )
        logger.info(f"Searching for .json file in : {stac_object.scene_id}")
        product_json_file = find_s3_filepaths_from_suffixes(
            bucket_name=s3_bucket,
            s3_folder=stac_object.s3_product_folder,
            suffixes=[".json"],
        )

        if make_existing_products or len(product_json_file[".json"]) == 0:
            if len(product_json_file[".json"]) > 0:
                logging.warning(
                    "Existing products will be replaced as --make-existing-products is set."
                )
            try:
                logger.info(f"uploading files for {stac_object.scene_id} to S3.")
                S3UPLOADER.push_files_in_folder_to_s3(
                    results_folder, s3_bucket, stac_object.s3_product_folder
                )
            except Exception as e:
                logger.error(
                    f"Failed to upload files for {stac_object.scene_id} to S3. Error: {e}"
                )
                raise

            # add basic info to the processed scene tracking file
            processed_scene_json["stac"].append(
                str(Path(stac_object.s3_product_folder) / Path(stac_filepath).name)
            )
        else:
            logging.info(
                "Skipping upload for existing product. Set --make-existing-products if this is not desired"
            )

    # upload the tracking file to a sub folder where it can be checked
    if not (skip_upload_processed_scene_tracking_file or skip_upload_to_s3):

        product_mode = scene.split("_")[1].lower()

        processed_scene_tracking_file_s3_folder = str(
            processed_scene_tracking_file_s3_folder / f"{product_mode}/processed_scenes"
        )

        processed_scene_tracking_file_s3_key = (
            f"{processed_scene_tracking_file_s3_folder}/{scene}.json"
        )
        logger.info(
            f"Uploading processed scene tracking file to S3 : {processed_scene_tracking_file_s3_key}."
        )
        try:
            S3UPLOADER.s3.put_object(
                Bucket=s3_bucket,
                Key=processed_scene_tracking_file_s3_key,
                Body=json.dumps(processed_scene_json, indent=2).encode("utf-8"),
                ContentType="application/json",
            )
        except Exception as e:
            logger.error(
                f"Failed to upload processed scene tracking file to S3 : {processed_scene_tracking_file_s3_key}. Error: {e}"
            )
            raise
