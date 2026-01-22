from datetime import datetime, timedelta
import logging
from pathlib import Path
import os
from shapely.geometry import shape
from pystac_client.exceptions import APIError
from tqdm import tqdm
import time
import json
import mimetypes

from sar_pipeline.utils.general import log_timing, format_dt_utc
from sar_pipeline.utils.spatial import load_geojson_as_multipolygon
from sar_pipeline.utils.sentinel1 import get_polarisation_list_from_scene_id
from sar_pipeline.utils.aws import find_s3_filepaths_from_suffixes, S3Util
from sar_pipeline.utils.antimeridian import (
    check_shape_crosses_antimeridian,
    get_bounds_for_antimeridian_shape,
)
from sar_pipeline.utils.stac import query_stac_for_metadata_in_period
from sar_pipeline.utils.dem import get_best_dem_type_for_scene, VALID_DEMS, ValidDemType
from sar_pipeline.pipelines.isce3_rtc.utils.burst_utils import (
    query_cdse_for_bursts_in_period,
)
from sar_pipeline.pipelines.isce3_rtc.metadata.odc import (
    make_rtc_s1_product_s3_prefix,
    make_rtc_s1_static_product_s3_prefix,
)
from sar_pipeline.pipelines.isce3_rtc.metadata.odc import (
    RTC_S1_S3_PREFIX_FORMAT,
    RTC_S1_STATIC_S3_PREFIX_FORMAT,
    get_odc_product_name,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


COMPLETENESS_REPORT_FORMAT = (
    "{report_dt}_{start_dt}_{end_dt}_{report_type}_completeness_report.json"
)
DEFAULT_S3_COMPLETENESS_REPORT_FOLDER = (
    "{s3_project_folder}/monitoring/completeness_reports"
)


def _make_completeness_report_json_safe(obj):
    """convert tuple keys to literal strings, datetimes to strings, Paths to strings"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            # --- key handling ---
            if isinstance(k, tuple):
                key = (
                    "("
                    + ", ".join(
                        repr(format_dt_utc(t) if isinstance(t, datetime) else str(t))
                        for t in k
                    )
                    + ")"
                )
            elif isinstance(k, Path):
                key = str(k)
            else:
                key = k

            out[key] = _make_completeness_report_json_safe(v)

        return out

    elif isinstance(obj, list):
        return [_make_completeness_report_json_safe(v) for v in obj]

    elif isinstance(obj, datetime):
        return format_dt_utc(obj)

    elif isinstance(obj, Path):
        return str(obj)

    else:
        return obj


@log_timing
def make_scene_completeness_report(
    s3_bucket: str,
    s3_project_folder: str,
    collection_number: str,
    start_dt: datetime,
    end_dt: datetime,
    roi_geojson: str | None,
    stac_catalog: str,
    s3_completeness_report_folder: str | None = None,
):
    """For variable descriptions and function docs see the cli:
    sar_pipeline/pipelines/isce3_rtc/monitoring/cli.py
    """
    logging.info(f"Running Sentinel-1 IW NRB Scene Level Completeness Check")

    if not s3_completeness_report_folder:
        logging.info(
            "`s3_completeness_report_folder` not provided. Report will be saved to subfolder "
            f"in provided `s3_project_folder` : {s3_project_folder}/monitoring/completeness_reports"
        )
        s3_completeness_report_folder = DEFAULT_S3_COMPLETENESS_REPORT_FOLDER.format(
            s3_project_folder=s3_project_folder
        )

    report_dt = datetime.now()

    completeness_report_name = COMPLETENESS_REPORT_FORMAT.format(
        report_dt=f"{report_dt.strftime('%Y%m%dT%H%M%S')}",
        start_dt=f"{start_dt.strftime('%Y%m%dT%H%M%S')}",
        end_dt=f"{end_dt.strftime('%Y%m%dT%H%M%S')}",
        report_type="scene",
    )

    # get the collections to search based on polarisations and collection_number
    # e.g. ga_s1_nrb_iw_hh_hv_1
    collections_to_search = [
        get_odc_product_name("RTC_S1", collection_number, ["VV"]),
        get_odc_product_name("RTC_S1", collection_number, ["HH"]),
        get_odc_product_name("RTC_S1", collection_number, ["VV", "VH"]),
        get_odc_product_name("RTC_S1", collection_number, ["HH", "HV"]),
    ]

    if isinstance(roi_geojson, str):
        geometry = load_geojson_as_multipolygon(roi_geojson).simplify(tolerance=0.1)

    logging.info("Query the CDSE STAC API for expected processed scene metadata")

    # stac query STAC for items with slight buffer in times
    n_stac_matches, stac_items = query_stac_for_metadata_in_period(
        start_dt=start_dt,
        end_dt=end_dt,
        geometry=shape(geometry),
        collections=["sentinel-1-slc"],
        query={"sar:instrument_mode": {"eq": "IW"}},
        fields={"include": ["id"]},
        stac_catalog="https://stac.dataspace.copernicus.eu/v1/",
    )

    if n_stac_matches == None:
        logging.info(f"Total number of matches not provided.")
    else:
        logging.info(
            f"{n_stac_matches} scenes found for the given time/geometry window."
        )

    logger.info("Iterating stac results. This may take a while for large requests...")

    # get the list of scenes we expect to have been processed based on the bursts
    expected_scene_set = {item["id"] for item in stac_items.items_as_dicts()}

    logging.info(
        f"{len(expected_scene_set)} processed scenes expected to be found for burst products"
    )

    # get the scenes that have been processed using the processed tracking file
    # this is a simple .json file that gets created after processing every scene
    # produced for sar-pipeline>v0.4.0
    processed_scene_s3_monitoring_folder = (
        f"{s3_project_folder}/monitoring/processed_scenes"
    )
    processed_scenes_set = set()

    logging.info(
        f"Searching the monitoring folder for processed scenes : {processed_scene_s3_monitoring_folder}"
    )

    # query the folder for the filenames (scene.json)
    s3_utility = S3Util()
    paginator = s3_utility.s3.get_paginator("list_objects_v2")
    found_any_objects = False

    for page in paginator.paginate(
        Bucket=s3_bucket,
        Prefix=processed_scene_s3_monitoring_folder,
    ):
        contents = page.get("Contents", [])
        if contents:
            found_any_objects = True

        for obj in contents:
            key = obj["Key"]
            if key.endswith(".json"):
                # add the scene_id
                processed_scenes_set.add(Path(key).stem)

    logging.info(
        f"{len(processed_scenes_set)} total processed scenes found for all locations and time"
    )

    # raise warning if folder is empty or does not exist
    if not found_any_objects:
        logger.warning(
            f"No objects found under s3://{s3_bucket}/"
            f"{processed_scene_s3_monitoring_folder}. "
            "Ensure that processed scenes are saved to this location in the isce3_rtc pipeline."
        )

        logger.warning(
            "Falling back to querying the STAC API for processed scenes. "
            "This is much slower and may not be appropriate for large time windows"
        )

        # query for bursts in the period and filter for scenes
        # this will happen for products made with sar-pipeline<=v0.4.0
        buffer = timedelta(minutes=1)
        n_stac_matches, stac_items = query_stac_for_metadata_in_period(
            start_dt=start_dt - buffer,
            end_dt=end_dt + buffer,
            geometry=shape(geometry),
            collections=collections_to_search,
            stac_catalog=stac_catalog,
            fields={"include": ["id", "properties.sarard:scene_id"]},
            # fields={"include": ["id", "properties.scene_id"]},
        )

        logging.info(
            f"{n_stac_matches} burst products found for the given time/geometry window.."
        )
        logging.info(f"Getting list of parent scenes processed")

        retries = 0
        max_retries = 1
        while True:
            try:
                for item in tqdm(
                    stac_items.items_as_dicts(),
                    total=n_stac_matches,
                    desc="Iterating STAC items",
                ):
                    processed_scenes_set.add(item["properties"]["sarard:scene_id"])
                break  # success
            except APIError as e:
                retries += 1
                if retries > max_retries:
                    break
                logging.warning(f"STAC API error: {e}. Retrying in 10s...")
                time.sleep(10)

    # reconcile which scenes do not exist / are missing and should therefore be reprocessed
    logger.info("Comparing list of processed scenes to expected scenes")
    existing_scene_set = expected_scene_set & processed_scenes_set
    missing_scene_set = expected_scene_set - processed_scenes_set

    logging.info(
        f"{len(existing_scene_set)} of {len(expected_scene_set)} expected products have been processed"
    )
    logging.info(
        f"{len(missing_scene_set)} of {len(expected_scene_set)} expected scenes are missing. "
        "For a detailed assessment of the specific burst products that need to be "
        "reprocessed or re-indexed run the burst level completeness check."
    )

    # Create the file detailing the missing products
    scene_completeness_dict = {
        "report_time": report_dt.strftime("%Y%m%dT%H%M%S"),
        "search_start_time": start_dt.strftime("%Y%m%dT%H%M%S"),
        "search_end_time": end_dt.strftime("%Y%m%dT%H%M%S"),
        "search_geometry": geometry.wkt,
        "search_roi_geojson": roi_geojson,
        "s3_bucket": s3_bucket,
        "s3_project_folder": s3_project_folder,
        "s3_completeness_report_folder": s3_completeness_report_folder,
        "collection_number": collection_number,
        "stac_catalog": stac_catalog,
        "collections_searched": collections_to_search,
        "nrb_product_format": RTC_S1_S3_PREFIX_FORMAT,
        "summary": {
            "n_expected_processed_scenes": len(expected_scene_set),
            "n_scenes_to_reprocess": len(missing_scene_set),
        },
        "results_descriptions": {
            "scenes_to_reprocess": "These are scenes that could not be found indexed in the open data cube (ODC). The simple assumption is made that these need to be reprocessed and indexed.",
        },
        "results": {
            "scenes_to_reprocess": list(missing_scene_set),
        },
    }

    scene_completeness_dict = _make_completeness_report_json_safe(
        scene_completeness_dict
    )

    os.makedirs("TMP/monitoring", exist_ok=True)
    with open(f"TMP/monitoring/{completeness_report_name}", "w") as f:
        json.dump(scene_completeness_dict, f, indent=2)

    # upload the completeness report to the desired AWS S3 bucket
    local_path = f"TMP/monitoring/{completeness_report_name}"
    s3_key = str(Path(s3_completeness_report_folder) / completeness_report_name)
    s3_utility.s3.upload_file(
        local_path,
        str(s3_bucket),
        s3_key,
        ExtraArgs={
            "ContentType": mimetypes.guess_type(local_path)[0] or "binary/octet-stream"
        },
    )
    logging.info(f"Uploaded {local_path} to s3://{s3_bucket}/{s3_key}")


@log_timing
def make_burst_product_completeness_report(
    s3_bucket: str,
    s3_project_folder: str,
    collection_number: str,
    start_dt: datetime,
    end_dt: datetime,
    roi_geojson: str | None,
    stac_catalog: str,
    s3_completeness_report_folder: str | None = None,
    identify_missing_linked_static_layers: bool = True,
    dem_type: ValidDemType = "best",
    static_layer_validity_start_date=20140403,
    linked_static_layer_s3_bucket: str | None = None,
    linked_static_layer_s3_project_folder: str | None = None,
    linked_static_layer_collection_number: str | None = None,
):
    """For variable descriptions and function docs see the cli:
    sar_pipeline/pipelines/isce3_rtc/monitoring/cli.py
    """

    logging.info(f"Running Sentinel-1 IW NRB Detailed Burst Level Completeness Check")

    if not s3_completeness_report_folder:
        logging.info(
            "`s3_completeness_report_folder` not provided. Report will be saved to subfolder "
            f"in provided `s3_project_folder` : {s3_project_folder}/monitoring/completeness_reports"
        )
        s3_completeness_report_folder = DEFAULT_S3_COMPLETENESS_REPORT_FOLDER.format(
            s3_project_folder=s3_project_folder
        )

    if dem_type not in VALID_DEMS:
        raise ValueError(
            f"Invalid dem_type {dem_type}. dem_type valid values are {VALID_DEMS}"
        )

    report_dt = datetime.now()
    # format for completeness report -> "{report_dt}_{start_dt}_{end_dt}_burst_completeness_report.json"

    completeness_report_name = COMPLETENESS_REPORT_FORMAT.format(
        report_dt=f"{report_dt.strftime('%Y%m%dT%H%M%S')}",
        start_dt=f"{start_dt.strftime('%Y%m%dT%H%M%S')}",
        end_dt=f"{end_dt.strftime('%Y%m%dT%H%M%S')}",
        report_type="burst",
    )

    if isinstance(roi_geojson, str):
        geometry = load_geojson_as_multipolygon(roi_geojson).simplify(tolerance=0.1)

    # Get the burst products we expect to have over the time period
    expected_burst_product_dict = query_cdse_for_bursts_in_period(
        start_dt=start_dt,
        end_dt=end_dt,
        chunk_query_minutes=5,
        geometry=geometry,
        query_overlap_seconds=10,
        product_type="IW_SLC__1S",
        max_workers=10,
    )

    # get the list of scenes we expect to have been processed based on the bursts
    expected_processed_scenes = list(
        set([v["scene_id"] for _, v in expected_burst_product_dict.items()])
    )

    # get the counts
    n_expected_products = len(expected_burst_product_dict)
    n_expected_scenes = len(expected_processed_scenes)

    # Get the burst products missing from the S3 bucket
    burst_products_not_in_s3 = {}
    burst_products_in_s3 = {}

    logger.info(
        f"Searching for nrb burst products missing from s3_bucket : {s3_bucket}, "
        f"s3_project_folder : {s3_project_folder}, "
        f"collection_number : {collection_number}, "
        f"aws_s3_prefix_format : {RTC_S1_S3_PREFIX_FORMAT} "
    )

    # TODO parallelise this
    for burst_id, azimuth_time in tqdm(
        expected_burst_product_dict.keys(), desc="Searching AWS for nrb products ..."
    ):
        # get the list of polarisations from the parent scene
        burst_polarisation_list = get_polarisation_list_from_scene_id(
            expected_burst_product_dict[(burst_id, azimuth_time)]["scene_id"]
        )

        # get the path to search for in s3
        expected_s3_product_folder = make_rtc_s1_product_s3_prefix(
            s3_project_folder=s3_project_folder,
            collection_number=collection_number,
            burst_polarisations=burst_polarisation_list,
            burst_id=burst_id,
            burst_st=azimuth_time,
        )

        # append the expected s3 path and pol list to the expected_burst_product_dict
        expected_burst_product_dict[(burst_id, azimuth_time)][
            "expected_s3_product_folder"
        ] = expected_s3_product_folder

        # assume the product exists if there is a stac-item.json file
        # logging.info(f"searching s3 folder : {expected_s3_product_folder}")
        product_stac_file = find_s3_filepaths_from_suffixes(
            bucket_name=s3_bucket,
            s3_folder=expected_s3_product_folder,
            suffixes=["stac-item.json"],
        )

        if len(product_stac_file["stac-item.json"]) > 0:
            # the product exists
            burst_products_in_s3[(burst_id, azimuth_time)] = (
                expected_burst_product_dict[(burst_id, azimuth_time)]
            )
        else:
            # the product does not exist
            burst_products_not_in_s3[(burst_id, azimuth_time)] = (
                expected_burst_product_dict[(burst_id, azimuth_time)]
            )

    # get the list of scenes with missing bursts not fully processed
    scenes_to_process = list(
        set([v["scene_id"] for _, v in burst_products_not_in_s3.items()])
    )

    # get the counts of the missing scenes and bursts to reprocess
    n_scenes_to_process = len(scenes_to_process)
    n_missing_from_s3 = len(burst_products_not_in_s3)
    logging.info(
        f"{n_missing_from_s3} of {n_expected_products} expected nrb burst products are missing."
    )
    logging.info(
        f"{n_scenes_to_process} of {n_expected_scenes} scenes are missing burst products."
    )

    # setup connection to the DEA STAC API
    logging.info(
        f"Connecting to STAC API catalog to check indexed products : {stac_catalog}"
    )

    # get the collections to search based on polarisations and collection_number
    # e.g. ga_s1_nrb_iw_hh_hv_1
    collections_to_search = [
        get_odc_product_name("RTC_S1", collection_number, ["VV"]),
        get_odc_product_name("RTC_S1", collection_number, ["HH"]),
        get_odc_product_name("RTC_S1", collection_number, ["VV", "VH"]),
        get_odc_product_name("RTC_S1", collection_number, ["HH", "HV"]),
    ]

    logging.info(f"Searching provided collections : {collections_to_search}")

    # stac query STAC for items with slight buffer in times
    buffer = timedelta(seconds=10)
    n_stac_matches, stac_items = query_stac_for_metadata_in_period(
        start_dt=start_dt - buffer,
        end_dt=end_dt + buffer,
        geometry=shape(geometry),
        collections=collections_to_search,
        stac_catalog=stac_catalog,
    )
    logging.info(f"{n_stac_matches} items found")

    # check which products are indexed and if there are any duplicates
    # that need to be archived.
    burst_products_indexed = {}
    burst_products_not_indexed = {}
    duplicate_products_to_archive = {}
    n_duplicate_products_to_archive = 0

    # determine which bursts are indexed
    # for i in range(0, 2): # uncomment to iterate through twice and ensure duplicates are found
    for burst_product in tqdm(
        stac_items.items_as_dicts(),
        total=n_stac_matches,
        desc="Iterating STAC items",
    ):
        odc_id = burst_product["id"]
        burst_id = burst_product["properties"]["sarard:burst_id"]
        azimuth_time = burst_product["properties"]["datetime"]
        created_time = burst_product["properties"]["created"]
        # convert dts
        azimuth_time = datetime.strptime(azimuth_time, "%Y-%m-%dT%H:%M:%S.%fZ")
        created_time = datetime.strptime(created_time, "%Y-%m-%dT%H:%M:%S.%fZ")

        if (burst_id, azimuth_time) not in expected_burst_product_dict:
            # additional product that is in the list of bursts from the CDSE
            # We have picked up with the expanded time buffer. Ignore.
            continue

        # Ensure the products is not already in our dictionary of indexed ones
        # and is therefore not a duplicate
        if (burst_id, azimuth_time) not in burst_products_indexed:
            # add the product to the list of indexed products with the
            # created time and odc product id
            burst_products_indexed[(burst_id, azimuth_time)] = (
                expected_burst_product_dict[(burst_id, azimuth_time)]
            )
            burst_products_indexed[(burst_id, azimuth_time)]["odc_id"] = odc_id
            burst_products_indexed[(burst_id, azimuth_time)]["created"] = created_time

        # we are dealing with a duplicate item
        else:

            n_duplicate_products_to_archive += 1

            # create a list of the duplicate products for a given burst
            if (burst_id, azimuth_time) not in duplicate_products_to_archive:
                duplicate_products_to_archive[(burst_id, azimuth_time)] = []

            # get the created date of the product already in the index list
            _existing_created_time = burst_products_indexed[(burst_id, azimuth_time)][
                "created"
            ]

            # if the incoming product is newer, we want to keep that and
            # archive the older product already in the dict
            if created_time > _existing_created_time:
                # incoming product is newer, add existing to list to archive
                archive_product = burst_products_indexed[
                    (burst_id, azimuth_time)
                ].copy()
                duplicate_products_to_archive[(burst_id, azimuth_time)].append(
                    archive_product
                )

                # update the information of the indexed product we want to keep
                # with the new odc product and created time
                burst_products_indexed[(burst_id, azimuth_time)]["odc_id"] = odc_id
                burst_products_indexed[(burst_id, azimuth_time)][
                    "created"
                ] = created_time

            # the incoming product is older, we want to archive this and leave
            # the current product in the indexed list
            else:
                archive_product = burst_products_indexed[
                    (burst_id, azimuth_time)
                ].copy()
                archive_product["created"] = created_time
                archive_product["odc_id"] = odc_id
                duplicate_products_to_archive[(burst_id, azimuth_time)].append(
                    archive_product
                )

    # make the dictionary of products not indexed
    burst_products_not_indexed = {
        k: v
        for k, v in expected_burst_product_dict.items()
        if k not in burst_products_indexed
    }
    n_missing_from_odc = len(burst_products_not_indexed)

    # get the products that need to be indexed. I.e. they exist in our storage
    # but are not indexed in the odc
    existing_burst_products_to_index = {
        k: v for k, v in burst_products_not_indexed.items() if k in burst_products_in_s3
    }
    n_existing_burst_products_to_index = len(existing_burst_products_to_index)

    logging.info(
        f"{n_missing_from_odc} of {n_expected_products} expected burst "
        f"products are not indexed and are missing from the ODC"
    )
    logging.info(
        f"{n_duplicate_products_to_archive} duplicate products have been "
        "found in the ODC and should be archived"
    )

    bursts_missing_static_layers = {}
    scenes_missing_static_layers = []

    if identify_missing_linked_static_layers:
        if n_scenes_to_process == 0:
            logging.info(f"All bursts have the required static layers.")
        else:
            logging.warning(
                "Searching for missing static layers for bursts. "
                "If a large number of scenes are missing this may take a long time. "
                "Set identify_missing_linked_static_layers = False or set "
                "--skip-identify-missing-linked-static-layers from the cli to skip this process"
            )
            logging.info("Query the CDSE STAC API for scene metadata")
            # stac query STAC for items with slight buffer in times
            buffer = timedelta(minutes=10)
            n_stac_matches, stac_items = query_stac_for_metadata_in_period(
                start_dt=start_dt - buffer,
                end_dt=end_dt + buffer,
                geometry=shape(geometry),
                collections=["sentinel-1-slc"],
                query={"sar:instrument_mode": {"eq": "IW"}},
                stac_catalog="https://stac.dataspace.copernicus.eu/v1/",
            )

            scene_dict = {
                item.id: item
                for item in stac_items.items()
                if item.id in scenes_to_process
            }

            logging.info(
                f"metadata found for {len(scene_dict)} of {n_scenes_to_process} scenes to process"
            )

            logger.info(
                f"Searching for static layers missing from s3_bucket : {linked_static_layer_s3_bucket}, "
                f"s3_project_folder : {linked_static_layer_s3_project_folder}, "
                f"collection_number : {linked_static_layer_collection_number}, "
                f"aws_s3_prefix_format : {RTC_S1_STATIC_S3_PREFIX_FORMAT}"
            )

            # temp supress logs for iteration
            root_logger = logging.getLogger()
            og_log_level = root_logger.level
            root_logger.setLevel(logging.WARNING)

            # TODO parallelise this
            for scene in tqdm(
                scenes_to_process,
                desc="Identifying missing static layers for unprocessed scenes",
            ):

                if dem_type == "best":
                    # we need to use the scene geometry to determine which DEM is used for the
                    # missing static layers
                    scene_poly = shape(scene_dict[scene].geometry)

                    # check if the scene crosses the antimeridian
                    if check_shape_crosses_antimeridian(scene_poly):
                        scene_bounds = get_bounds_for_antimeridian_shape(scene_poly)
                    else:
                        scene_bounds = scene_poly.bounds

                    scene_dem_type = get_best_dem_type_for_scene(scene_bounds)
                    logger.info(f"Scene requires the DEM : {scene_dem_type}")
                else:
                    scene_dem_type = dem_type

                # get the list of bursts that belong to that scene
                scene_bursts = [
                    k
                    for k, v in expected_burst_product_dict.items()
                    if v["scene_id"] == scene
                ]

                # iterate through the burst ids
                for burst_id, azimuth_time in scene_bursts:

                    # construct the s3_prefix for the static layer to search if it exists
                    expected_static_layer_s3_product_folder = make_rtc_s1_static_product_s3_prefix(
                        s3_project_folder=linked_static_layer_s3_project_folder,
                        collection_number=linked_static_layer_collection_number,
                        dem_type=scene_dem_type,
                        static_layer_validity_start_date=static_layer_validity_start_date,
                        burst_id=burst_id,
                    )
                    # logging.info(
                    #     f"searching for static layers in s3 folder : {expected_static_layer_s3_product_folder}"
                    # )
                    # assume the product exists if there is a .h5 file
                    product_h5_file = find_s3_filepaths_from_suffixes(
                        bucket_name=s3_bucket,
                        s3_folder=expected_static_layer_s3_product_folder,
                        suffixes=[".h5"],
                    )

                    if len(product_h5_file[".h5"]) == 0:
                        # the product does not exist
                        bursts_missing_static_layers[(burst_id, azimuth_time)] = (
                            expected_burst_product_dict[(burst_id, azimuth_time)]
                        )
                        bursts_missing_static_layers[(burst_id, azimuth_time)][
                            "expected_static_layer_s3_product_folder"
                        ] = expected_static_layer_s3_product_folder
                        if scene not in scenes_missing_static_layers:
                            scenes_missing_static_layers.append(scene)

    # return logger to original level
    root_logger.setLevel(og_log_level)

    # get the counts of the missing static layers
    n_bursts_missing_static_layers = len(bursts_missing_static_layers)
    n_scenes_missing_static_layers = len(scenes_missing_static_layers)

    if identify_missing_linked_static_layers:
        logging.info(
            f"Number of bursts missing static layers : {n_bursts_missing_static_layers}"
        )
        logging.info(
            f"Number of scenes missing static layers : {n_scenes_missing_static_layers}"
        )

    # Create the file with missing products
    completeness_dict = {
        "report_time": report_dt.strftime("%Y%m%dT%H%M%S"),
        "search_start_time": start_dt.strftime("%Y%m%dT%H%M%S"),
        "search_end_time": end_dt.strftime("%Y%m%dT%H%M%S"),
        "search_geometry": geometry.wkt,
        "search_roi_geojson": roi_geojson,
        "s3_bucket": s3_bucket,
        "s3_project_folder": s3_project_folder,
        "s3_completeness_report_folder": s3_completeness_report_folder,
        "collection_number": collection_number,
        "stac_catalog": stac_catalog,
        "collections_searched": collections_to_search,
        "nrb_product_format": RTC_S1_S3_PREFIX_FORMAT,
        "identify_missing_linked_static_layers": identify_missing_linked_static_layers,
        "linked_static_layer_product_format": RTC_S1_STATIC_S3_PREFIX_FORMAT,
        "linked_static_layer_s3_bucket": linked_static_layer_s3_bucket,
        "linked_static_layer_s3_project_folder": linked_static_layer_s3_project_folder,
        "linked_static_layer_collection_number": linked_static_layer_collection_number,
        "summary": {
            "n_expected_processed_scenes": n_expected_scenes,
            "n_expected_burst_products": n_expected_products,
            "n_scenes_to_reprocess": n_scenes_to_process,
            "n_burst_products_missing_from_aws_s3_bucket": n_missing_from_s3,
            "n_burst_products_missing_from_odc": n_missing_from_odc,
            "n_burst_products_to_reprocess": n_missing_from_s3,
            "n_burst_products_existing_to_index": n_existing_burst_products_to_index,
            "n_burst_products_to_archive": n_duplicate_products_to_archive,
            "n_bursts_products_with_missing_static_layers_to_reprocess": n_bursts_missing_static_layers,
            "n_scenes_with_missing_static_layers_to_reprocess": n_scenes_missing_static_layers,
        },
        "results_descriptions": {
            "scenes_to_reprocess": "These are scenes that contain burst products that cannot be found in storage and therefore need to be reprocessed.",
            "burst_products_to_reprocess": "These are the burst products that cannot be found in storage and therefore need to be reprocessed.",
            "burst_products_existing_to_index": "These are products that exist in storage, but are missing from the open data cube (ODC). They therefore need to be indexed.",
            "burst_products_to_archive": "These are duplicate products found in the open data cube (ODC) that should be archived. The most recent version of the duplicate product will remain.",
            "scenes_with_missing_static_layers_to_reprocess": "These are the scenes that contain missing static layers for the given burst_ids. Static layers for these need to be processed before backscatter products (burst_products_to_reprocess) can be created.",
            "bursts_products_with_missing_static_layers_to_reprocess": "These are the missing static layers for the given burst_ids. Static layers for these need to be processed before backscatter products (burst_products_to_reprocess) can be created.",
        },
        "results": {
            "scenes_to_reprocess": scenes_to_process,
            "burst_products_to_reprocess": burst_products_not_in_s3,
            "burst_products_existing_to_index": existing_burst_products_to_index,
            "burst_products_to_archive": duplicate_products_to_archive,
            "scenes_with_missing_static_layers_to_reprocess": scenes_missing_static_layers,
            "bursts_products_with_missing_static_layers_to_reprocess": bursts_missing_static_layers,
        },
    }

    # make the keys (burst_id, azimuth_time) a string so it can be saved as a json
    # convert the datetimes to strings too
    completeness_json = _make_completeness_report_json_safe(completeness_dict)

    os.makedirs("TMP/monitoring", exist_ok=True)
    with open(f"TMP/monitoring/{completeness_report_name}", "w") as f:
        json.dump(completeness_json, f, indent=2)

    # upload the completeness report to the desired AWS S3 bucket
    s3_uploder = S3Util()
    local_path = f"TMP/monitoring/{completeness_report_name}"
    s3_key = str(Path(s3_completeness_report_folder) / completeness_report_name)
    s3_uploder.s3.upload_file(
        local_path,
        str(s3_bucket),
        s3_key,
        ExtraArgs={
            "ContentType": mimetypes.guess_type(local_path)[0] or "binary/octet-stream"
        },
    )
    logger.info(f"summary : {json.dumps(completeness_json['summary'], indent=2)}")
    logging.info(f"Uploaded {local_path} to s3://{s3_bucket}/{s3_key}")
