import click
import logging
from pathlib import Path
import shutil
import sys
import shapely
from shapely.geometry import mapping
from s1reader import s1_info
import re

from sar_pipeline.preparation.downloads.scenes import (
    download_scene_from_preference_list,
    VALID_SCENE_DATA_SOURCES,
)
from sar_pipeline.preparation.downloads.orbits import (
    download_orbits,
    VALID_ORBIT_DATA_SOURCES,
)
from sar_pipeline.pipelines.isce3_rtc.utils.burst_utils import (
    ensure_static_layers_in_s3,
    check_burst_product_h5_exists_in_s3,
    get_burst_info_for_scene_from_cdse,
    get_burst_info_for_scene_from_asf,
)

from sar_pipeline.pipelines.isce3_rtc.utils.config_manager import RTCConfigManager
from sar_pipeline.pipelines.isce3_rtc.metadata.stac import BurstH5toStacManager
from sar_pipeline.pipelines.isce3_rtc.metadata.odc import (
    make_static_layer_browse_url,
    make_rtc_s1_burst_browse_url,
)
from sar_pipeline.pipelines.isce3_rtc.metadata.xml import XMLMapper
from sar_pipeline.utils.s3upload import push_files_in_folder_to_s3
from sar_pipeline.utils.general import log_timing
from sar_pipeline.utils.spatial import (
    write_burst_geometries_to_geojson,
)
from sar_pipeline.utils.antimeridian import (
    check_shape_crosses_antimeridian,
    get_bounds_for_antimeridian_shape,
)
from sar_pipeline.utils.checksum import PackageChecksum

from dem_handler.dem.cop_glo30 import get_cop30_dem_for_bounds
from dem_handler.dem.rema import get_rema_dem_for_bounds
from dem_handler.utils.spatial import (
    check_dem_type_in_bounds,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VALID_DEMS = [
    "cop_glo30",
    "REMA_32",
    "REMA_10",
    "REMA_2",
    "REMA_10_TIMESERIES",
    "REMA_30_TIMESERIES",
    "REMA_32_TIMESERIES",
]


@click.command()
@click.option(
    "--scene",
    type=str,
    required=True,
    help="scene id. E.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD",
)
@click.option(
    "--burst-id-list",
    required=False,
    type=str,
    help="List of burst IDs separated by space. e.g. t070_149815_iw2 t070_149815_iw3",
)
@click.option(
    "--resolution",
    required=True,
    type=int,
    help="The desired resolution of the final product (metres)",
)
@click.option(
    "--output-crs",
    required=False,
    default="",
    help="The output CRS as an integer. e.g. 3031. If [None,'UTM','utm'] the default UTM zone for scene/burst center is used (polar stereo at lat>75).",
)
@click.option(
    "--dem-type",
    required=True,
    type=str,
    help="The type of DEM that should be downloaded for processing the scene. "
    "Can be passed as a string or list of preferences separated by a space. "
    "If DEM data does not exist in the area of the first preference, the next will be used. "
    "E.g. `--dem-type REMA_32 cop_glo30` will first look for the Antarctic specific REMA DEM @32m before settling on the cop_glo30. "
    f"Values must be one of {VALID_DEMS}",
)
@click.option(
    "--product",
    required=True,
    type=click.Choice(["RTC_S1", "RTC_S1_STATIC"]),
    help="The product to be made",
)
@click.option(
    "--backscatter-convention",
    required=False,
    default="gamma0",
    type=click.Choice(["gamma0", "sigma0", "beta0"]),
    help="Backscatter convention of the product to be made (gamma0, sigma0 or beta0). "
    "Note, sigma0 data is referenced to the DEM. See docs for information on creating ellipsoid referenced sigma0 data.",
)
@click.option(
    "--s3-bucket",
    required=True,
    type=str,
    help="S3 bucket where the product will be uploaded",
)
@click.option(
    "--s3-project-folder",
    required=True,
    type=str,
    help="project folder in the s3 bucket",
)
@click.option(
    "--collection-number",
    required=True,
    type=int,
    help="The collection number of the product.",
)
@click.option(
    "--download-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder where downloaded files should go",
)
@click.option(
    "--scratch-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder where scratch files go",
)
@click.option(
    "--out-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder where final products will be written",
)
@click.option(
    "--run-config-save-path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Path to where the RTC/opera config wil be saved",
)
@click.option(
    "--make-existing-products",
    required=False,
    is_flag=True,
    default=False,
    help="Create the burst products even if they already exist in the desired s3 bucket path. "
    "WARNING - setting this argument may result in duplicate files.",
)
@click.option(
    "--link-static-layers",
    required=False,
    is_flag=True,
    default=False,
    help="If static layers should be linked to RTC_S1 products in the"
    "STAC metadata. A url to the static layers will be added"
    "to the run config file.",
)
@click.option(
    "--linked-static-layers-s3-bucket",
    required=False,
    type=str,
    help="S3 bucket containing the RTC_S1_STATIC data that will be linked to the RTC_S1 bursts.",
)
@click.option(
    "--linked-static-layers-collection-number",
    required=False,
    type=str,
    help="Collection number of RTC_S1_STATIC data that will be linked to the RTC_S1 bursts.",
)
@click.option(
    "--linked-static-layers-s3-project-folder",
    required=False,
    type=str,
    help="Project folder containing the RTC_S1_STATIC data that will be linked to the RTC_S1 bursts. ",
)
@click.option(
    "--scene-data-source",
    required=False,
    default=["AUS_COP_HUB", "ASF", "CDSE"],
    type=str,
    help="Where to download the scene from. "
    "Can be passed as a string or list of preferences separated by a space. "
    "If the scene cannot be found at the first preference, the next will be used. "
    "E.g. `--scene-data-source AUS_COP_HUB CDSE` will first try to download the scene from "
    "The Copernicus Australasia Regional Data Hub before moving to try from the European CDSE. "
    "Credentials for the desired data source must be set as environment variables."
    f"Values must be one of {VALID_SCENE_DATA_SOURCES}",
)
@click.option(
    "--orbit-data-source",
    required=False,
    default=["ASF", "CDSE"],
    type=str,
    help="Where to download the orbit files from. "
    "Can be passed as a string or list of preferences separated by a space. "
    "If the orbits files cannot be found at the first preference, the next will be used. "
    "E.g. `--orbit-data-source CDSE ASF` will first try to download the orbit files from "
    "The CDSE before moving to try from the ASF. "
    "Credentials for the desired data source must be set as environment variables."
    f"Values must be one of {VALID_ORBIT_DATA_SOURCES}",
)
@click.option("--make-folders", required=False, default=True, help="Create folders")
@click.option(
    "--save-burst-geometries",
    required=False,
    default=True,
    is_flag=True,
    help="Save the burst geometries to a geojson",
)
@click.option(
    "--rema-year",
    required=False,
    help="Year of the REMA data to use. Format: YYYY-MM for monthly data or YYYY for yearly data." \
    "If not specified, the year is automatically extracted from the scene acquisition date. ",
    default="0",  # If set to zero the rema_year is automatically extracted from the scene acquisition date. 
    # This is only relevant for the REMA timeseries DEM options. For non-timeseries DEM options, this argument is ignored.
)
@log_timing
def get_data_for_scene_and_make_run_config(
    scene,
    burst_id_list,
    resolution,
    output_crs,
    dem_type,
    product,
    backscatter_convention,
    s3_bucket,
    s3_project_folder,
    collection_number,
    download_folder,
    scratch_folder,
    out_folder,
    run_config_save_path,
    make_existing_products,
    link_static_layers,
    linked_static_layers_s3_bucket,
    linked_static_layers_collection_number,
    linked_static_layers_s3_project_folder,
    scene_data_source,
    orbit_data_source,
    make_folders,
    save_burst_geometries,
    rema_year,
):
    """Download the required data for the RTC/opera and create a configuration
    file for the run that points to appropriate files and has the required settings
    """

    logger.info(f"Downloading data for scene : {scene}")
    logger.info(f"Data source for scene download : {scene_data_source}")
    logger.info(f"Data source for orbit download : {orbit_data_source}")

    # get the preference list of dem types
    dem_types = dem_type.split(" ")
    if not all([d in VALID_DEMS for d in dem_types]):
        raise ValueError(
            f"Invalid --dem_type {dem_types}. --dem-type valid values are {VALID_DEMS}"
        )
    logger.info(f"The order of DEM preference is : {dem_types}")

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

    # make the base .yaml for RTC processing
    if product == "RTC_S1":
        RTC_RUN_CONFIG = RTCConfigManager(base_config="S1_RTC.yaml")
    elif product == "RTC_S1_STATIC":
        RTC_RUN_CONFIG = RTCConfigManager(base_config="S1_RTC_STATIC.yaml")
    else:
        raise ValueError("product must be S1_RTC or S1_RTC_STATIC")

    if backscatter_convention not in ["gamma0", "sigma0", "beta0"]:
        raise ValueError("backscatter_convention must be one of gamma0, sigma0, beta0")

    # sub-folders for downloads
    orbit_folder = download_folder / "orbits"
    scene_folder = download_folder / "scenes"

    if make_folders:
        logger.info(f"Making output folders if not existing")
        download_folder.mkdir(parents=True, exist_ok=True)
        orbit_folder.mkdir(parents=True, exist_ok=True)
        scene_folder.mkdir(parents=True, exist_ok=True)
        out_folder.mkdir(parents=True, exist_ok=True)
        scratch_folder.mkdir(parents=True, exist_ok=True)
        run_config_save_path.parent.mkdir(parents=True, exist_ok=True)

    # The burst ids, start-times and geometries can be acquired from the ASF/CDSE.
    # We can therefore check if desired products already exist before needing to download the scene
    try:
        logger.info(f"Querying ASF for scene burst ids")
        all_scene_burst_info = get_burst_info_for_scene_from_asf(scene)
        logger.info(
            f"{len(all_scene_burst_info)} burst ids found for scene from ASF API"
        )
    except Exception:
        logger.info(f"Burst ids not found on ASF, trying the CDSE", exc_info=True)
        try:
            logger.info(f"Querying CDSE for scene burst ids")
            all_scene_burst_info = get_burst_info_for_scene_from_cdse(scene)
            logger.info(
                f"{len(all_scene_burst_info)} burst ids found for scene from CDSE API"
            )
        except Exception:
            logger.error(
                f"Burst ids could not be found for scene on ASF or CDSE. Check input scene : {scene}",
                exc_info=True,
            )
            raise

    # Limit the bursts to be processed if a list has been provided
    if burst_id_list:
        logger.info(f"List of bursts to process provided")
        burst_id_list_candidates = burst_id_list.split(" ")

    else:
        logger.info(f"List of bursts not provided, processing all")
        burst_id_list_candidates = list(all_scene_burst_info.keys())

    logger.info(
        f"Checking if burst products already exists in S3 for product {product}"
    )
    burst_st_list_candidates = [
        all_scene_burst_info[id_]["start_time"] for id_ in burst_id_list_candidates
    ]
    polarisation_list = [
        pol
        for id_ in burst_id_list_candidates
        for pol in all_scene_burst_info[id_]["pols"]
    ]
    polarisation_list = list(set(polarisation_list))
    # return products that don't exist, and early exit if all already exist
    burst_id_list_to_process = check_burst_product_h5_exists_in_s3(
        product=product,
        burst_id_list=burst_id_list_candidates,
        burst_st_list=burst_st_list_candidates,
        burst_polarisations=polarisation_list,
        s3_bucket=s3_bucket,
        s3_project_folder=s3_project_folder,
        collection_number=collection_number,
        make_existing_products=make_existing_products,
        early_exit=True,
        early_exit_code=100,
    )
    logger.info(
        f"Processing {len(burst_id_list_to_process)} bursts for scene : {burst_id_list_to_process}"
    )

    # to link the RTC_S1_STATIC layers to RTC_S1, the static layers must already exist
    if link_static_layers and product == "RTC_S1":
        logger.info(f"Checking static layers exist for bursts in scene : {scene}")
        # the process will exit early if the required static layers don't exist
        ensure_static_layers_in_s3(
            scene=scene,
            burst_id_list=burst_id_list_to_process,
            static_layers_s3_bucket=linked_static_layers_s3_bucket,
            static_layers_collection_number=linked_static_layers_collection_number,
            static_layers_s3_project_folder=linked_static_layers_s3_project_folder,
            early_exit_code=101,
        )

    # iterate through the preferences for the scene data source and download the scene
    SCENE_PATH, scene_polygon, input_scene_url = download_scene_from_preference_list(
        scene_data_source_preferences=scene_data_sources,
        scene=scene,
        download_folder=scene_folder,
        unzip=True,
    )

    # # download the orbits
    logger.info(f"Downloading Orbits for scene : {scene}")
    ORBIT_PATH = download_orbits(
        scene_safe_file=scene + ".SAFE",
        save_dir=orbit_folder,
        source=orbit_data_sources,
    )
    logger.info(f"File downloaded to : {ORBIT_PATH}")

    # show the original scene shape and bounds
    logger.info(f"The scene shape is : {scene_polygon}")
    logger.info(f"The scene bounds are : {scene_polygon.bounds}")

    # get the shape of the area covering the bursts to be processed
    burst_geoms_to_process = [
        all_scene_burst_info[id_]["geometry"] for id_ in burst_id_list_to_process
    ]
    # write the geometries to a geojson. Useful for debugging if needed
    if save_burst_geometries:
        write_burst_geometries_to_geojson(
            burst_id_list_to_process,
            burst_geoms_to_process,
            out_folder / f"{scene}_burst_geoms.json",
        )

    # check if the scene shape crosses the antimeridian
    # different antimeridian shapes are returned from the CDSE (Polygon) and ASF (multipolygon)
    if check_shape_crosses_antimeridian(scene_polygon):
        logger.warning("The scene crosses the antimeridian")
        # use the full scene bounds for an antimeridian scene
        bounds = get_bounds_for_antimeridian_shape(scene_polygon)
        logger.info(
            f"Getting the corrected scene bounds crossing the antimeridian : {bounds}"
        )
        logger.info("Using the bounds for complete scene over the antimeridian.")
        cop30_buffer_degrees = 0.5  # slighly bigger buffer
    else:
        # reduce the DEM download by considering only the required bursts geometries
        # if all bursts are considered, this will be close to the scene bounds
        combined_burst_geom = shapely.ops.unary_union(burst_geoms_to_process)
        logger.info(
            f"The shape covering the required bursts is : {combined_burst_geom}"
        )
        logger.info(
            f"The bounds covering the required bursts are : {combined_burst_geom.bounds}"
        )
        logger.info("Using the bounds for the required bursts.")

        bounds = combined_burst_geom.bounds
        cop30_buffer_degrees = 0.3

    logger.info(f"Finding the best DEM in order of preference: {dem_types}")
    for dem_type in dem_types:
        if dem_type == "cop_glo30":
            dem_resolution = 30
        elif dem_type in ["REMA_32", "REMA_10", "REMA_2"]:
            dem_resolution = int(dem_type.split("_")[1])
            rema_year = None
        elif dem_type in [
            "REMA_32_TIMESERIES",
            "REMA_30_TIMESERIES",
            "REMA_10_TIMESERIES",
        ]:
            dem_resolution = int(dem_type.split("_")[1])
            if rema_year == "0":  # if the rema_year argument is set to the default value, extract the year from the scene acquisition date
                rema_year = int(scene.split("_")[5][0:4])  # year from aq date
            else:
                logger.info(f"Fixing REMA year to the user specified value : {rema_year}")
        # For REMA v0.5 with 30m resolution, this check is skipped in dem-handler and later the bounds are checked when the DEM data is downloaded.
        dem_in_bounds = check_dem_type_in_bounds(dem_type, dem_resolution, bounds)
        if dem_in_bounds:
            # dem has data in the bounds we want, exit with dem_type set
            break
        elif dem_type == dem_types[-1] and not dem_in_bounds:
            logger.warning(
                "No DEM data could not be found in the requested bounds. "
                "The bursts will be processed with ellipsoidal heights. "
                "Change `dem_type` if this is not desired."
            )

    dem_folder = download_folder / "dem" / dem_type
    DEM_PATH = dem_folder / f"{scene}_dem.tif"
    if make_folders:
        dem_folder.mkdir(parents=True, exist_ok=True)

    logger.info(f"Downloading DEM type `{dem_type}` to path : {DEM_PATH}")
    if dem_type == "cop_glo30":
        get_cop30_dem_for_bounds(
            bounds=bounds,
            save_path=DEM_PATH,
            ellipsoid_heights=True,
            adjust_at_high_lat=True,
            buffer_pixels=None,
            buffer_degrees=cop30_buffer_degrees,
            cop30_folder_path=dem_folder,
            geoid_tif_path=dem_folder / f"{scene}_geoid.tif",
            download_dem_tiles=True,
            download_geoid=True,
        )
    elif dem_type in [
        "REMA_32",
        "REMA_10",
        "REMA_2",
        "REMA_32_TIMESERIES",
        "REMA_30_TIMESERIES",
        "REMA_10_TIMESERIES",
    ]:
        get_rema_dem_for_bounds(
            bounds=bounds,
            rema_year=rema_year,
            bounds_src_crs=4326,
            save_path=DEM_PATH,
            resolution=dem_resolution,
            buffer_pixels=1200,
            ellipsoid_heights=True,
            download_geoid=True,
            geoid_tif_path=dem_folder / f"{scene}_geoid.tif",
            download_dir=dem_folder,
        )
    else:
        raise ValueError(f"dem_type must be one of {VALID_DEMS}")

    # Update input and ancillary data
    logger.info(f"Updating the run config for scene")
    gk = "runconfig.groups"
    RTC_RUN_CONFIG.set(f"{gk}.input_file_group.safe_file_path", [str(SCENE_PATH)])
    RTC_RUN_CONFIG.set(
        f"{gk}.input_file_group.source_data_access",
        input_scene_url,
    )
    RTC_RUN_CONFIG.set(f"{gk}.input_file_group.orbit_file_path", [str(ORBIT_PATH)])
    RTC_RUN_CONFIG.set(f"{gk}.dynamic_ancillary_file_group.dem_file", str(DEM_PATH))

    # set the backscatter convention and if rtc_apply is true
    if backscatter_convention == "beta0":
        RTC_RUN_CONFIG.set(f"{gk}.processing.apply_rtc", False)
        # note output_type is still set to gamma0, but it is ignored as apply_rtc=False
    else:
        RTC_RUN_CONFIG.set(f"{gk}.processing.apply_rtc", True)
        RTC_RUN_CONFIG.set(f"{gk}.processing.rtc.output_type", backscatter_convention)

    # set the dem input source
    if dem_type == "cop_glo30":
        demSource = "https://registry.opendata.aws/copernicus-dem/"
        demDescription = f"Copernicus Global 30m DEM - {demSource}"
    elif dem_type in ["REMA_32", "REMA_10", "REMA_2"]:
        dem_res = dem_type.split("_")[-1]
        demSource = (
            f"https://data.pgc.umn.edu/elev/dem/setsm/REMA/mosaic/v2.0/{dem_res}m"
        )
        demDescription = f"Reference Elevation Model of Antarctica (REMA) DEM at {dem_res}m - {demSource}"
    elif dem_type in ["REMA_32_TIMESERIES", "REMA_30_TIMESERIES", "REMA_10_TIMESERIES"]:
        dem_res = dem_type.split("_")[-2]
        demSource = "https://umn1.osn.mghpcc.org"
        demDescription = f"Reference Elevation Model of Antarctica (REMA) DEM timeseries at {dem_res}m - {demSource}"
    else:
        raise ValueError(f"dem_type must be one of {VALID_DEMS}")

    RTC_RUN_CONFIG.set(
        f"{gk}.dynamic_ancillary_file_group.dem_file_description", demDescription
    )

    # specify bursts to process
    RTC_RUN_CONFIG.set(f"{gk}.input_file_group.burst_id", burst_id_list_to_process)

    # Update Outputs
    RTC_RUN_CONFIG.set(f"{gk}.product_group.output_dir", str(out_folder))
    RTC_RUN_CONFIG.set(f"{gk}.product_group.scratch_path", str(scratch_folder))

    # check if the collection_number passed in aligns with the
    # product_version specified in the config
    prod_version = RTC_RUN_CONFIG.get(f"{gk}.product_group.product_version")
    prod_version_collection_number = int(re.split(r"[-.]", prod_version)[0])
    if prod_version_collection_number != collection_number:
        logger.warning(
            f"The specified collection_number is {collection_number}. However, "
            f"the product_version in the config template is : {prod_version}. "
            f"The product_version format is <collection_number>.<minor_version>.<patch_version> "
            f"and should align with the specified collection_number. One of these should be updated. "
            f"The path to the config is {RTC_RUN_CONFIG.file_path}."
        )

    # NOTE - In the future, we may want to make this dynamic. E.g. multi-temporal DEMS
    # Currently set to a fixed value in the run config template.
    # RTC_RUN_CONFIG.set(
    #     f"{gk}.product_group.rtc_s1_static_validity_start_date", 20140403
    # )

    if link_static_layers or (product == "RTC_S1_STATIC"):
        # add the static layer base url
        # the '{burst_id}' string gets handled in the RTC process and ensures
        # the burst id is appended to each .h5 and Geotiff file
        static_layer_data_access = make_static_layer_browse_url(
            linked_static_layers_s3_bucket,
            linked_static_layers_collection_number,
            linked_static_layers_s3_project_folder,
            burst_id="{burst_id}",
        )
        logger.info(f"static layer data access : {static_layer_data_access}")
        RTC_RUN_CONFIG.set(
            f"{gk}.product_group.static_layers_data_access",
            str(static_layer_data_access),
        )

    # add the link to access the product
    # the '{burst_id}' string gets handled in the RTC process and ensures
    # the burst id is appended to each .h5 and Geotiff file
    if product == "RTC_S1_STATIC":
        RTC_RUN_CONFIG.set(
            f"{gk}.product_group.product_data_access",
            str(static_layer_data_access),
        )
    else:
        burst_product_data_access = make_rtc_s1_burst_browse_url(
            s3_bucket=s3_bucket,
            s3_project_folder=s3_project_folder,
            collection_number=collection_number,
            burst_polarisations=polarisation_list,
            burst_id="{burst_id}",
        )
        RTC_RUN_CONFIG.set(
            f"{gk}.product_group.product_data_access",
            str(burst_product_data_access),
        )

    # set the polarisation
    POLARIZATION_TYPE = (
        "dual-pol" if len(polarisation_list) > 1 else "co-pol"
    )  # string for template value
    RTC_RUN_CONFIG.set(f"{gk}.processing.polarization", POLARIZATION_TYPE)

    # update the burst resolution
    bk = "runconfig.groups.processing.geocoding.bursts_geogrid"
    RTC_RUN_CONFIG.set(f"{bk}.x_posting", int(resolution))
    RTC_RUN_CONFIG.set(f"{bk}.y_posting", int(resolution))
    RTC_RUN_CONFIG.set(f"{bk}.x_snap", int(resolution))
    RTC_RUN_CONFIG.set(f"{bk}.y_snap", int(resolution))

    # update the burst crs if it has been set and is not UTM | utm
    if output_crs and (output_crs not in ["utm", "UTM"]):
        RTC_RUN_CONFIG.set(f"{bk}.output_epsg", int(output_crs))

    # save the config
    logger.info(f"Saving config to : {run_config_save_path}")
    RTC_RUN_CONFIG.save(run_config_save_path)


@click.command()
@click.option(
    "--results-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the folder containing the burst outputs from RTC/opera",
)
@click.option(
    "--run-config-path",
    required=True,
    type=click.Path(dir_okay=False, path_type=Path),
    help="Path to the config path used to run RTC opera",
)
@click.option(
    "--product",
    required=True,
    type=click.Choice(["RTC_S1", "RTC_S1_STATIC"]),
    help="The product being made. Determines bucket structure",
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
    required=True,
    type=int,
    help="The collection number of the product.",
)
@click.option(
    "--s3-bucket", required=True, type=str, help="The bucket to upload the files"
)
@click.option(
    "--s3-project-folder",
    required=True,
    type=str,
    help="The folder within the bucket to upload the files. Note the "
    "final path follows the patter in the description of this function.",
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
    help="Create the burst products even if they already exist in the desired s3 bucket path. "
    "WARNING - setting this argument may result in duplicate files.",
)
@click.option(
    "--link-static-layers",
    required=False,
    is_flag=True,
    default=False,
    help="If static layers should be linked to RTC_S1 products in the"
    "STAC metadata. If set, the url to the static layer collection will "
    "be read in from the .h5 output from the rtc_s1.py process.",
)
@click.option(
    "--linked-static-layers-s3-bucket",
    required=False,
    type=str,
    help="S3 bucket containing the RTC_S1_STATIC data that will be linked to the RTC_S1 bursts.",
)
@click.option(
    "--linked-static-layers-collection-number",
    required=False,
    type=str,
    help="Collection number of RTC_S1_STATIC data that will be linked to the RTC_S1 bursts.",
)
@click.option(
    "--linked-static-layers-s3-project-folder",
    required=False,
    type=str,
    help="Project folder containing the RTC_S1_STATIC data that will be linked to the RTC_S1 bursts. ",
)
@click.option(
    "--validate-stac",
    required=False,
    is_flag=True,
    default=False,
    help="Whether to validate the stac document within the code. "
    "If the stac is not valid, an error is raised and the products "
    "will not be uploaded.",
)
@log_timing
def make_rtc_opera_stac_and_upload_bursts(
    results_folder,
    run_config_path,
    product,
    backscatter_convention,
    collection_number,
    s3_bucket,
    s3_project_folder,
    skip_upload_to_s3,
    make_existing_products,
    link_static_layers,
    linked_static_layers_s3_bucket,
    linked_static_layers_collection_number,
    linked_static_layers_s3_project_folder,
    validate_stac,
):
    """makes STAC metadata for opera-rtc and uploads them to a desired s3 bucket.
    The final path in s3 will follow the following pattern:
    product = RTC_S1:
        s3_bucket/s3_folder/odc_product_name/burst_id/burst_year/burst_month/burst_day/*files
    product = RTC_S1_STATIC:
        s3_bucket/s3_folder/odc_product_name/burst_id/*files
    """

    # iterate through the burst directory and create STAC metadata
    logger.info(
        f"Iterating through the burst folders to reformat files and create STAC metadata"
    )
    burst_folders = [x for x in results_folder.iterdir() if x.is_dir()]

    for i, burst_folder in enumerate(burst_folders):
        logger.info(
            f"Making STAC metadata for burst {i+1} of {len(burst_folders)} : {burst_folder}"
        )

        logger.info(
            f"Renaming all files so 'v' is not in the product version number, version is '-' separated, and the platform name is lowercase (e.g s1a)."
        )
        for product_file in burst_folder.iterdir():
            if product_file.is_file():
                # step 1: remove 'v' before version numbers
                name = re.sub(r"v(?=\d)", "", product_file.name)
                # step 2: replace version pattern digits.digits.digits → digits-digits-digits
                name = re.sub(r"(\d+)\.(\d+)\.(\d+)", r"\1-\2-\3", name)
                # step 3: lowercase the platform (S1 + single letter, anywhere)
                name = re.sub(r"S1[A-Z]", lambda m: m.group(0).lower(), name)
                new_path = product_file.with_name(name)
                if new_path != product_file:
                    logger.info(f"Renaming: {product_file.name} -> {new_path.name}")
                    product_file.rename(new_path)

        # load in the .h5 file containing metadata for each burst
        burst_h5_files = list(burst_folder.glob("*.h5"))
        if len(burst_h5_files) != 1:
            raise ValueError(
                f"{len(burst_h5_files)} .h5 files found. Expecting 1 in : {burst_folder}."
                f"This error might be caused by repeat runs. Delete duplicate files or change run settings."
            )
        burst_h5_filepath = burst_folder / burst_h5_files[0]

        # get the product name common to files from the .h5
        # e.g. ga_s1_nrb-static_v0.1.0_T070-149815-IW3_20140403
        burst_product_name = burst_h5_filepath.stem.replace("_metadata", "")

        # rename the .h5 file to conform with ga naming conventions
        burst_h5_filepath = burst_h5_filepath.rename(
            burst_folder / f"{burst_product_name}_metadata.h5"
        )
        # copy the run config file to the burst folder and rename to conform with ga naming conventions
        burst_run_config_filepath = (
            burst_folder / f"{burst_product_name}_proc-config.yaml"
        )
        shutil.copy(run_config_path, burst_run_config_filepath)

        # create a placeholder checksum file to link in stac metadata
        checksum_filepath = burst_folder / f"{burst_product_name}_checksum.sha1"
        Path(checksum_filepath).touch()

        # make the stac metadata from the .h5 metadata
        logging.info(f"Making stac metadata from .h5 file")
        # initialise the class to convert data from the .h5 to a stac doc
        if product == "RTC_S1":
            logger.info(
                "STAC geometry will be set using valid data from a product GeoTiff"
            )
            update_geometry_using_valid_data = True
        else:
            update_geometry_using_valid_data = False
            logger.info("STAC geometry will be set using data from the .h5 file")
        burst_stac_manager = BurstH5toStacManager(
            h5_filepath=burst_h5_filepath,
            product=product,
            product_id=burst_product_name,
            backscatter_convention=backscatter_convention,
            update_geometry_using_valid_data=update_geometry_using_valid_data,
            collection_number=collection_number,
            s3_bucket=s3_bucket,
            s3_project_folder=s3_project_folder,
        )

        # make the stac item from the .h5 file
        burst_stac_manager.make_stac_item_from_h5()
        # add properties to the stac doc
        logging.info(f"Adding properties from .h5 file")
        burst_stac_manager.add_properties_from_h5()
        # rename the backscatter assets to include calibration and conform to ga naming conventions
        logging.info(f"Renaming asset files")
        burst_stac_manager.rename_asset_files(burst_folder)
        logging.info(f"Adding assets to stac doc")
        burst_stac_manager.add_assets_from_folder(burst_folder)
        # add additional links that will rarely change
        logging.info(f"Adding fixed links")
        burst_stac_manager.add_fixed_links()
        logging.info(f"Adding dynamic links from h5")
        burst_stac_manager.add_dynamic_links_from_h5()
        if link_static_layers and product == "RTC_S1":
            # link to static layer metadata is in the .h5 file
            # use this to map assets to the file
            logger.info("Linking static layers to product")
            burst_stac_manager.add_linked_static_layers_as_assets_to_stac(
                linked_static_layers_s3_bucket=linked_static_layers_s3_bucket,
                linked_static_layers_collection_number=linked_static_layers_collection_number,
                linked_static_layers_s3_project_folder=linked_static_layers_s3_project_folder,
            )
        logging.info(f"Adding links to metadata files and self")
        # set the filepaths for stac and xml data if applicable
        stac_filepath = burst_folder / f"{burst_product_name}_stac-item.json"
        if product == "RTC_S1":
            xml_filepath = burst_folder / f"{burst_product_name}_metadata.xml"
        else:
            xml_filepath = None  # no xml for static layers
        # add additional links to metadata files. e.g. stac, xml, proc config
        burst_stac_manager.add_metadata_links(
            stac_filepath=stac_filepath,
            h5_filepath=burst_h5_filepath,
            runconfig_filepath=burst_run_config_filepath,
            xml_filepath=xml_filepath,
        )
        # reference the production stac catalogue for collection number > 0
        logging.info(f"Adding stac collection link")
        burst_stac_manager.add_collection_link(PRODUCTION=collection_number > 0)
        # save the metadata
        burst_stac_manager.save(stac_filepath)
        if validate_stac:
            logger.info("Validating STAC document")
            try:
                burst_stac_manager.item.validate()
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
        # create the XML file from the existing metadata files
        if xml_filepath:
            logger.info("Creating the XML file from the stac and .h5 metadata files")
            XML = XMLMapper(
                stac_path=stac_filepath,
                h5_path=burst_h5_filepath,
                polarisations=burst_stac_manager.polarisations,
                backscatter_convention=backscatter_convention,
            )
            logger.info("Populating the XML template using the mapping file")
            XML.populate_xml()
            logger.info(
                f"Adding special mappings to XML template. e.g. multiple backscatter pols"
            )
            XML.populate_special_xml_mappings()
            logger.info(f"Saving XML file to : {xml_filepath}")
            XML.save_xml(xml_filepath)

        # replace the empty checksum file now all required files have been created
        product_checksum = PackageChecksum()
        checksum_files = [f for f in burst_folder.iterdir() if "checksum" not in str(f)]
        product_checksum.add_files(checksum_files)
        product_checksum.write(checksum_filepath)

        # push folder to S3
        if skip_upload_to_s3:
            logger.info(f"Skipping upload to S3.")
        else:
            # re-check that the files don't already exist in S3. This will help protect against
            # simultaneous runs of the same product. E.g. the product did not exist at the
            # start of the run and was created by another process during this runtime
            logger.info(
                f"Checking if product already exist before uploading for burst : {burst_stac_manager.burst_id}"
            )
            # returns a list of bursts that don't already exist
            # pass in just the current burst
            bursts_to_upload = check_burst_product_h5_exists_in_s3(
                product=product,
                burst_id_list=[burst_stac_manager.burst_id],
                burst_st_list=[burst_stac_manager.start_dt],
                burst_polarisations=burst_stac_manager.polarisations,
                s3_bucket=s3_bucket,
                s3_project_folder=s3_project_folder,
                collection_number=collection_number,
                make_existing_products=make_existing_products,
                early_exit=False,  # don't exit early, move to next burst
            )
            if burst_stac_manager.burst_id in bursts_to_upload:
                logger.info(f"uploading files for {burst_stac_manager.burst_id} to S3.")
                push_files_in_folder_to_s3(
                    burst_folder, s3_bucket, burst_stac_manager.burst_s3_subfolder
                )
            else:
                logger.info(f"Skipping upload to S3.")


from sar_pipeline import PROJECT_ROOT_PATH
from sar_pipeline.utils.aws import S3Util
from sar_pipeline.analysis.compare_folder import compare_product_folder_files
from sar_pipeline.analysis.compare_metadata import (
    compare_json,
    compare_xml,
    write_diffs_to_json,
    write_diffs_to_xml,
)
from sar_pipeline.analysis.compare_cog import compare_cog_stats
import os
import json


@click.command()
@click.option(
    "--product",
    required=True,
    type=click.Choice(["RTC_S1", "RTC_S1_STATIC"]),
    help="The product type being compared",
)
@click.option(
    "--local-product-folder-1",
    required=False,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the local folder containing the first burst outputs from RTC/opera to compare",
)
@click.option(
    "--local-product-folder-2",
    required=False,
    type=click.Path(file_okay=False, path_type=Path),
    help="Path to the local folder containing the second burst outputs from RTC/opera to compare",
)
@click.option(
    "--s3-product-folder-1",
    required=False,
    type=str,
    help="Path to the folder in s3 containing the first burst outputs from RTC/opera to compare."
    " Ensure AWS_ACCESS_KEY_ID, AWS_ACCESS_KEY_SECRET, AWS_DEFAULT_REGION environment variables set if required.",
)
@click.option(
    "--s3-product-folder-2",
    required=False,
    type=str,
    help="Path to the folder in s3 containing the second burst outputs from RTC/opera to compare."
    "Ensure AWS_ACCESS_KEY_ID, AWS_ACCESS_KEY_SECRET, AWS_DEFAULT_REGION environment variables set if required.",
)
@click.option(
    "--s3-bucket",
    required=False,
    default="deant-data-public-dev",
    type=str,
    help="S3 where outputs are being stored. Required if s3 folders are set as input",
)
@click.option(
    "--out-folder",
    required=False,
    default=PROJECT_ROOT_PATH / "comparison",
    type=click.Path(file_okay=False, path_type=Path),
    help="Folder to write the outputs of the comparison to",
)
def compare_products(
    product,
    local_product_folder_1,
    local_product_folder_2,
    s3_product_folder_1,
    s3_product_folder_2,
    s3_bucket,
    out_folder,
):
    logger.info(f"The product being compared is : {product}")
    logger.info(f"The outputs will be written to : {out_folder}")

    if not out_folder.exists():
        raise ValueError(
            f"Specified --out-folder does not exist, please create: {out_folder}"
        )

    if not (s3_product_folder_1 or local_product_folder_1):
        logger.error(
            "Ensure either --local-product-folder-1 or --s3-product-folder-1 set"
        )
        raise ValueError
    elif not (s3_product_folder_2 or local_product_folder_2):
        logger.error(
            "Ensure either --local-product-folder-2 or --s3-product-folder-2 set"
        )
        raise ValueError

    if s3_product_folder_1 or s3_product_folder_2:
        # set up the AWS download util
        S3Downloader = S3Util()

    if s3_product_folder_1:
        # download product folder to local folder
        local_product_folder_1 = out_folder / "folder_1" / s3_product_folder_1
        os.makedirs(local_product_folder_1, exist_ok=True)
        S3Downloader.download_folder(
            s3_bucket, s3_product_folder_1, local_product_folder_1
        )
    if s3_product_folder_2:
        # download product folder to local folder
        local_product_folder_2 = out_folder / "folder_2" / s3_product_folder_2
        os.makedirs(local_product_folder_2, exist_ok=True)
        S3Downloader.download_folder(
            s3_bucket, s3_product_folder_2, local_product_folder_2
        )

    # compare count of files and filetypes in folder
    files_are_different, file_differences = compare_product_folder_files(
        local_product_folder_1, local_product_folder_2
    )
    file_differences_path = out_folder / "file_differences.json"
    if files_are_different:
        logging.warning(
            f"Differences in product files found. Saving summary to : {file_differences_path}"
        )
    else:
        logger.info(
            f"No differences in product files identified. Saving summary to : {file_differences_path}"
        )
    write_diffs_to_json(file_differences, file_differences_path)

    # compare the json files
    json_files_1 = list(local_product_folder_1.glob("*.json"))
    json_files_2 = list(local_product_folder_2.glob("*.json"))
    if len(json_files_1) > 1:
        logging.error("Multiple jsons found for product 1, expecting 1 per product")
        raise ValueError
    if len(json_files_2) > 1:
        logging.error("Multiple jsons found for product 2, expecting 1 per product")
        raise ValueError

    json_differences = compare_json(str(json_files_1[0]), str(json_files_2[0]))
    json_difference_path = out_folder / "json_differences.json"
    if len(json_differences) > 0:
        logging.warning(
            f"Differences in json metadata found. Saving summary to : {json_difference_path}"
        )
    else:
        logger.info(
            f"No differences in json file identified. Saving summary to : {json_difference_path}"
        )
    write_diffs_to_json(json_differences, json_difference_path)

    if product == "RTC_S1":
        # compare the xml files - xml only exits for rtc_s1
        xml_files_1 = list(local_product_folder_1.glob("*.xml"))
        xml_files_2 = list(local_product_folder_2.glob("*.xml"))
        if len(xml_files_1) > 1:
            logging.error("Multiple xmls found in product 1, expecting 1")
            raise ValueError
        if len(xml_files_2) > 1:
            logging.error("Multiple xmls found in product 2, expecting 1")
            raise ValueError

        xml_differences = compare_xml(str(xml_files_1[0]), str(xml_files_2[0]))
        xml_difference_path = out_folder / "xml_differences.xml"
        if len(xml_differences) > 0:
            logging.warning(
                f"Differences in xml metadata found. Saving summary to : {xml_difference_path}"
            )
        else:
            logger.info(
                f"No differences in XML file identified. Saving summary to : {xml_difference_path}"
            )
        write_diffs_to_xml(xml_differences, xml_difference_path)

    # compare the like tifs. e.g. compare mask to mask, HH-gamma0 to HH-gamma0
    # e.g. tif_1 = ga_s1a_nrb_0-1-0_T070-149815-IW3_20211220T124752Z_HH-gamma0.tif # new product created now
    # e.g. tif_2 = ga_s1a_nrb_0-1-0_T070-149815-IW3_20211220T124752Z_HH-gamma0.tif # existing to compare
    logger.info("Comparing the tifs between products")
    tif_files_1 = set(local_product_folder_1.glob("*.tif"))
    tif_files_2 = set(local_product_folder_2.glob("*.tif"))
    tif_comparison_stats = {}
    tif_difference_path = out_folder / "tif_differences.json"
    for tif_1 in tif_files_1:
        filetype = tif_1.stem.split("_")[
            -1
        ]  # i.e. mask, HH-gamma0, local_incidence_angle
        if not files_are_different:
            # we have the exact same tif naming and can compare directly
            tif_2 = local_product_folder_2 / tif_1.name
            logger.info(f"Comparing tif statistics of filetype : {filetype}")
            tifs_are_same, stats = compare_cog_stats(tif_1, tif_2)
            tif_comparison_stats[filetype] = stats
        else:
            tif_2 = [x for x in tif_files_2 if filetype in x]
            if not tif_2:
                logger.warning(
                    f'Could not find tif of same filetype "{filetype}" to compare with {tif_1}'
                )
                continue
            elif len(tif_2) > 1:
                logger.error(
                    f'Multiple tif files found for file type "{filetype}", expecting 1. Skipping comparison'
                )
                continue
            else:
                logger.info(f"Comparing tif statistics of filetype : {filetype}")
                tifs_are_same, stats = compare_cog_stats(tif_1, tif_2[0])
                tif_comparison_stats[filetype] = stats

        if not tifs_are_same:
            logging.warning(
                f"Differences in tif statistics found. Saving summary to : {tif_difference_path}"
            )
        else:
            logger.info(
                f"No differences in tif statistics found. Saving summary to : {tif_difference_path}"
            )
        write_diffs_to_json(tif_comparison_stats, tif_difference_path)
