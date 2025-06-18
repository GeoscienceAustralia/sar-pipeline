import click
import logging
from pathlib import Path
import shutil
import sys
from shapely.geometry import shape
from s1reader import s1_info
import re

from sar_pipeline.aws.preparation.scenes import (
    download_slc_from_asf,
    download_slc_from_cdse,
)
from sar_pipeline.aws.preparation.orbits import download_orbits
from sar_pipeline.aws.preparation.burst_utils import (
    check_static_layers_in_s3,
    make_static_layer_base_url,
    check_burst_products_exists_in_s3,
    get_burst_ids_and_start_times_for_scene_from_asf,
)

from sar_pipeline.aws.preparation.config import RTCConfigManager
from sar_pipeline.aws.metadata.stac import BurstH5toStacManager
from sar_pipeline.utils.s3upload import push_files_in_folder_to_s3
from sar_pipeline.utils.general import log_timing

from dem_handler.dem.cop_glo30 import get_cop30_dem_for_bounds
from dem_handler.dem.rema import get_rema_dem_for_bounds
from dem_handler.utils.spatial import (
    check_s1_bounds_cross_antimeridian,
    get_correct_bounds_from_shape_at_antimeridian,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


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
    type=click.Choice(["cop_glo30", "REMA_32", "REMA_10", "REMA_2"]),
    help="The type of DEM that should be downloaded for processing the scene.",
)
@click.option(
    "--product",
    required=True,
    type=click.Choice(["RTC_S1", "RTC_S1_STATIC"]),
    help="The product to be made",
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
    "--collection",
    required=True,
    type=str,
    help="collection associated with product. e.g. s1_rtc_c1. Must end in 'cX' where X is an "
    "integer number referring to the collection.",
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
    "STAC metadata. A url to the static layer collection will be added"
    "to the run config file.",
)
@click.option(
    "--linked-static-layers-s3-bucket",
    required=False,
    type=str,
    help="S3 bucket containing the RTC_S1_STATIC data that will be linked to the RTC_S1 bursts.",
)
@click.option(
    "--linked-static-layers-collection",
    required=False,
    type=str,
    help="Collection of RTC_S1_STATIC data that will be linked to the RTC_S1 bursts.",
)
@click.option(
    "--linked-static-layers-s3-project-folder",
    required=False,
    type=str,
    help="Project folder containing the RTC_S1_STATIC data that will be linked to the RTC_S1 bursts. "
    "Expected for linked files path is : s3_bucket/s3_project_folder/collection/burst_id/*files",
)
@click.option(
    "--scene-data-source",
    required=False,
    default="CDSE",
    type=click.Choice(["ASF", "CDSE"]),
    help="Where to download the scene from.",
)
@click.option(
    "--orbit-data-source",
    required=False,
    default="CDSE",
    type=click.Choice(["ASF", "CDSE"]),
    help="Where to download the scene from.",
)
@click.option("--make-folders", required=False, default=True, help="Create folders")
@log_timing
def get_data_for_scene_and_make_run_config(
    scene,
    burst_id_list,
    resolution,
    output_crs,
    dem_type,
    product,
    s3_bucket,
    s3_project_folder,
    collection,
    download_folder,
    scratch_folder,
    out_folder,
    run_config_save_path,
    make_existing_products,
    link_static_layers,
    linked_static_layers_s3_bucket,
    linked_static_layers_collection,
    linked_static_layers_s3_project_folder,
    scene_data_source,
    orbit_data_source,
    make_folders,
):
    """Download the required data for the RTC/opera and create a configuration
    file for the run that points to appropriate files and has the required settings
    """

    logger.info(f"Downloading data for scene : {scene}")
    logger.info(f"Data source for scene download : {scene_data_source}")
    logger.info(f"Data source for orbit download : {orbit_data_source}")

    # make the base .yaml for RTC processing
    if product == "RTC_S1":
        RTC_RUN_CONFIG = RTCConfigManager(base_config="S1_RTC.yaml")
    elif product == "RTC_S1_STATIC":
        RTC_RUN_CONFIG = RTCConfigManager(base_config="S1_RTC_STATIC.yaml")
    else:
        raise ValueError("product must be S1_RTC or S1_RTC_STATIC")

    # ensure the collection ends with cX, where X is a positive integer
    collection_number = re.search(r"c(\d+)$", collection)
    if not collection_number:
        raise ValueError(
            f"Invalid collection name. The collection MUST end in cX where X"
            " is an integer associated with the collection. E.g. rtc_s1_c1."
        )

    # sub-folders for downloads
    orbit_folder = download_folder / "orbits"
    scene_folder = download_folder / "scenes"
    dem_folder = download_folder / "dem" / dem_type

    if make_folders:
        logger.info(f"Making output folders if not existing")
        download_folder.mkdir(parents=True, exist_ok=True)
        orbit_folder.mkdir(parents=True, exist_ok=True)
        scene_folder.mkdir(parents=True, exist_ok=True)
        dem_folder.mkdir(parents=True, exist_ok=True)
        out_folder.mkdir(parents=True, exist_ok=True)
        scratch_folder.mkdir(parents=True, exist_ok=True)
        run_config_save_path.parent.mkdir(parents=True, exist_ok=True)

    if scene_data_source == "ASF":
        # the burst ids and start-times can be acquired from the asf-search api.
        # We can therefore check if products already exist before needing to download the scene
        logger.info(f"Querying ASF for scene burst id's")
        all_slc_burst_id_list, all_slc_burst_st_list = (
            get_burst_ids_and_start_times_for_scene_from_asf(scene)
        )
        logger.info(
            f"{len(all_slc_burst_id_list)} burst ids found for scene from ASF API"
        )

    elif scene_data_source == "CDSE":
        try:
            # try to find bursts on ASF first so download is not done until required
            logger.info(f"Querying ASF for scene burst id's")
            all_slc_burst_id_list, all_slc_burst_st_list = (
                get_burst_ids_and_start_times_for_scene_from_asf(scene)
            )
            logger.info(
                f"{len(all_slc_burst_id_list)} burst ids found for scene from ASF API"
            )
            SCENE_PATH = None  # set flag so we know to download
        except FileExistsError:
            logger.info(f"Burst id's not found on ASF, downloading scene from CDSE")
            # burst information must be taken from a downloaded scene
            logger.info(f"Downloading SLC for scene : {scene}")
            SCENE_PATH, cdse_scene_metadata = download_slc_from_cdse(
                scene, scene_folder
            )
            scene_polygon = shape(cdse_scene_metadata["geometry"])
            polarisation_list = cdse_scene_metadata["properties"]["polarisation"].split(
                "&"
            )
            input_scene_url = cdse_scene_metadata["properties"]["services"]["download"][
                "url"
            ]
            # get burst data from the downloaded slc
            slc_bursts_info = []
            logger.info(f"Getting burst information from the downloaded scene slc file")
            logger.info(f"Scene polarisations : {polarisation_list}")
            for pol in polarisation_list:
                slc_bursts_info += s1_info.get_bursts(SCENE_PATH, pol=pol.lower())
                all_slc_burst_id_list = [str(b.burst_id) for b in slc_bursts_info]
                all_slc_burst_st_list = [b.sensing_start for b in slc_bursts_info]

            logger.info(
                f"{len(all_slc_burst_id_list)} burst ids found for scene in the slc"
            )

    # Limit the bursts to be processed if a list has been provided
    if burst_id_list:
        logger.info(f"List of bursts to process provided")
        burst_id_list = burst_id_list.split(" ")
        burst_st_list = [
            all_slc_burst_st_list[i]
            for i, b in enumerate(all_slc_burst_id_list)
            if b in burst_id_list
        ]
    else:
        logger.info(f"List of bursts not provided, processing all")
        burst_id_list = all_slc_burst_id_list
        burst_st_list = all_slc_burst_st_list

    logger.info(
        f"Checking if burst products already exists in S3 for product {product}"
    )
    burst_id_list = check_burst_products_exists_in_s3(
        product=product,
        burst_id_list=burst_id_list,
        burst_st_list=burst_st_list,
        s3_bucket=s3_bucket,
        s3_project_folder=s3_project_folder,
        collection=collection,
        make_existing_products=make_existing_products,
    )

    logger.info(f"Processing {len(burst_id_list)} bursts for scene : {burst_id_list}")

    # to link the RTC_S1_STATIC layers to RTC_S1, the static layers must already exist
    if link_static_layers and product == "RTC_S1":
        logger.info(f"Checking static layers exist for bursts in scene : {scene}")
        check_static_layers_in_s3(
            scene=scene,
            burst_id_list=burst_id_list,
            static_layers_s3_bucket=linked_static_layers_s3_bucket,
            static_layers_collection=linked_static_layers_collection,
            static_layers_s3_project_folder=linked_static_layers_s3_project_folder,
        )

    if scene_data_source == "ASF":
        # download the SLC and get scene metadata from asf
        logger.info(f"Downloading SLC for scene : {scene}")
        SCENE_PATH, asf_scene_metadata = download_slc_from_asf(scene, scene_folder)
        scene_polygon = shape(asf_scene_metadata.geometry)
        polarisation_list = asf_scene_metadata.properties["polarization"].split("+")
        input_scene_url = asf_scene_metadata.properties["url"]

    elif scene_data_source == "CDSE" and SCENE_PATH is None:
        logger.info(f"Downloading SLC for scene : {scene}")
        SCENE_PATH, cdse_scene_metadata = download_slc_from_cdse(scene, scene_folder)
        scene_polygon = shape(cdse_scene_metadata["geometry"])
        polarisation_list = cdse_scene_metadata["properties"]["polarisation"].split("&")
        input_scene_url = cdse_scene_metadata["properties"]["services"]["download"][
            "url"
        ]

    # # download the orbits
    logger.info(f"Downloading Orbits for scene : {scene}")
    ORBIT_PATHS = download_orbits(
        sentinel_file=scene + ".SAFE", save_dir=orbit_folder, source=orbit_data_source
    )
    logger.info(f"File downloaded to : {ORBIT_PATHS[0]}")

    # # download the dem
    DEM_PATH = dem_folder / f"{scene}_dem.tif"
    bounds = scene_polygon.bounds

    logger.info(f"The scene shape is : {scene_polygon}")
    logger.info(f"The scene bounds are : {bounds}")

    if check_s1_bounds_cross_antimeridian(bounds):
        # the scene crosses the antimeridian, the bounds need to be
        # correctly obtained from the source shape
        logger.warning("The scene crosses the antimeridian, correcting bounds")
        bounds = get_correct_bounds_from_shape_at_antimeridian(scene_polygon)
        logger.info(f"The scene bounds are : {bounds}")
        # increase the buffer to ensure DEM sufficiently covers area
        # shape is a little odd due to merging either side of AM
        cop30_buffer_degrees = 0.8
    else:
        cop30_buffer_degrees = 0.3

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
    elif dem_type in ["REMA_32", "REMA_10", "REMA_2"]:
        dem_resolution = int(dem_type.split("_")[1])
        get_rema_dem_for_bounds(
            bounds=bounds,
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
        raise ValueError(
            'dem_type must be one of ["cop_glo30","REMA_32","REMA_10","REMA_2"]'
        )

    # Update input and ancillary data
    logger.info(f"Updating the run config for scene")
    gk = "runconfig.groups"
    RTC_RUN_CONFIG.set(f"{gk}.input_file_group.safe_file_path", [str(SCENE_PATH)])
    RTC_RUN_CONFIG.set(
        f"{gk}.input_file_group.source_data_access",
        input_scene_url,
    )
    RTC_RUN_CONFIG.set(f"{gk}.input_file_group.orbit_file_path", [str(ORBIT_PATHS[0])])
    RTC_RUN_CONFIG.set(f"{gk}.dynamic_ancillary_file_group.dem_file", str(DEM_PATH))

    # set the dem input source
    if dem_type == "cop_glo30":
        demSource = "https://registry.opendata.aws/copernicus-dem/"
        RTC_RUN_CONFIG.set(
            f"{gk}.dynamic_ancillary_file_group.dem_file_description", demSource
        )

    if burst_id_list:
        # specify bursts if provided
        RTC_RUN_CONFIG.set(f"{gk}.input_file_group.burst_id", burst_id_list)

    # Update Outputs
    RTC_RUN_CONFIG.set(f"{gk}.product_group.output_dir", str(out_folder))
    RTC_RUN_CONFIG.set(f"{gk}.product_group.scratch_path", str(scratch_folder))
    if product == "RTC_S1_STATIC":
        # TODO YYYYMMDD
        RTC_RUN_CONFIG.set(
            f"{gk}.product_group.rtc_s1_static_validity_start_date", 20010101
        )

    if link_static_layers:
        # add the static layer base url
        static_layer_base_url = make_static_layer_base_url(
            linked_static_layers_s3_bucket,
            linked_static_layers_collection,
            linked_static_layers_s3_project_folder,
        )
        logger.info(f"static layer base url : {static_layer_base_url}")
        RTC_RUN_CONFIG.set(
            f"{gk}.product_group.static_layers_data_access", str(static_layer_base_url)
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
    "--collection",
    required=True,
    type=str,
    help="collection associated with product. e.g. s1_rtc_c1. Must end in 'cX' where X is an "
    "integer number referring to the collection.",
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
    "--link-static-layers",
    required=False,
    is_flag=True,
    default=False,
    help="If static layers should be linked to RTC_S1 products in the"
    "STAC metadata. If set, the url to the static layer collection will "
    "be read in from the .h5 output from the rtc_s1.py process.",
)
@log_timing
def make_rtc_opera_stac_and_upload_bursts(
    results_folder,
    run_config_path,
    product,
    collection,
    s3_bucket,
    s3_project_folder,
    skip_upload_to_s3,
    link_static_layers,
):
    """makes STAC metadata for opera-rtc and uploads them to a desired s3 bucket.
    The final path in s3 will follow the following pattern:
    s3_bucket/s3_folder/collection/burst_id/burst_year/burst_month/burst_day/*files
    """

    # iterate through the burst directory and create STAC metadata
    burst_folders = [x for x in results_folder.iterdir() if x.is_dir()]
    for i, burst_folder in enumerate(burst_folders):
        logger.info(
            f"Making STAC metadata for burst {i+1} of {len(burst_folders)} : {burst_folder}"
        )
        # copy the run config file to the burst folder
        shutil.copy(run_config_path, burst_folder / run_config_path.name)
        # load in the .h5 file containing metadata for each burst
        burst_h5_files = list(burst_folder.glob("*.h5"))
        if len(burst_h5_files) != 1:
            raise ValueError(
                f"{len(burst_h5_files)} .h5 files found. Expecting 1 in : {burst_folder}."
                f"This error might be caused by repeat runs. Delete duplicate files or change run setings."
            )
        burst_h5_filepath = burst_folder / burst_h5_files[0]
        # make the stac metadata from the .h5 metadata
        logging.info(f"Making stac metadata from .h5 file")
        # initialise the class to convert data from the .h5 to a stac doc
        burst_stac_manager = BurstH5toStacManager(
            h5_filepath=burst_h5_filepath,
            product=product,
            collection=collection,
            s3_bucket=s3_bucket,
            s3_project_folder=s3_project_folder,
        )
        # make the stac item based
        burst_stac_manager.make_stac_item_from_h5()
        # add properties to the stac doc
        # TODO finalise stac metadata
        burst_stac_manager.add_properties_from_h5()
        # add the assets to the stac doc
        burst_stac_manager.add_assets_from_folder(burst_folder)
        # add additional links that will rarely change
        burst_stac_manager.add_fixed_links()
        # add links that can change
        burst_stac_manager.add_dynamic_links_from_h5()
        # add the link to self/metadata
        if link_static_layers and product == "RTC_S1":
            # link to static layer metadata is in the .h5 file
            # use this to map assets to the file
            burst_stac_manager.add_linked_static_layer_assets_and_link()
        stac_filename = "metadata.json"
        burst_stac_manager.add_self_link(filename=stac_filename)
        # TODO add final link to the collection STAC
        burst_stac_manager.add_collection_link()
        # save the metadata
        burst_stac_manager.save(burst_folder / stac_filename)
        # TODO validate the stac item when finalised
        logger.info("Validating STAC document")
        try:
            # burst_stac_manager.item.validate()
            logger.info("STAC is valid.")
        except Exception as e:
            logger.error(f"STAC validation failed: {e}")
            raise
        # push folder to S3
        if skip_upload_to_s3:
            logger.info(f"Skipping upload to S3.")
        else:
            logger.info(f"uploading files for {burst_stac_manager.burst_id} to S3.")
            push_files_in_folder_to_s3(
                burst_folder, s3_bucket, burst_stac_manager.burst_s3_subfolder
            )
