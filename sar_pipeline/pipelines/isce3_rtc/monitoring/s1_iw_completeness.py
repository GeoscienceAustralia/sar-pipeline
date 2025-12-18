from datetime import datetime, timedelta
from typing import Optional, Literal
import requests
import logging
import shapely
from pathlib import Path
import os
from shapely.geometry import shape, Polygon, MultiPolygon
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import re
import pandas as pd
import pystac_client
import json
from odc.stac import load, configure_s3_access
from pprint import pprint

from sar_pipeline.utils.general import log_timing
from sar_pipeline.utils.sentinel1 import get_polarisation_list_from_scene_id
from sar_pipeline.utils.aws import find_s3_filepaths_from_suffixes, S3Util
from sar_pipeline.utils.antimeridian import (
    check_shape_crosses_antimeridian,
    get_bounds_for_antimeridian_shape,
)
from sar_pipeline.utils.dem import get_best_dem_type_for_scene, VALID_DEMS, ValidDemType
from sar_pipeline.preparation.downloads.scenes import query_scene_from_cdse
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

ValidBurstProducts = Literal["IW_SLC__1S", "EW_SLC__1S"]


def _format_dt(dt: datetime) -> str:
    s = dt.strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    return re.sub(r"(\.\d{3})\d{3}Z$", r"\1Z", s)


def make_completeness_report_json_safe(obj):
    """convert tuple keys to literal strings and convert datetimes to strings"""
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            # --- key handling ---
            if isinstance(k, tuple):
                key = (
                    "("
                    + ", ".join(
                        repr(_format_dt(t) if isinstance(t, datetime) else t) for t in k
                    )
                    + ")"
                )
            else:
                key = k

            out[key] = make_completeness_report_json_safe(v)

        return out

    elif isinstance(obj, list):
        return [make_completeness_report_json_safe(v) for v in obj]

    elif isinstance(obj, datetime):
        return _format_dt(obj)

    else:
        return obj


def _make_chunk_request(
    base_url: str,
    chunk_start: datetime,
    chunk_end: datetime,
    product_type: str,
    geometry: Optional[Polygon | MultiPolygon],
):
    """Execute a single GET request for one time chunk."""
    chunk_start = _format_dt(chunk_start)
    chunk_end = _format_dt(chunk_end)

    base_query = (
        f"$filter=ContentDate/Start ge {chunk_start} "
        f"and ContentDate/Start le {chunk_end} "
        f"and ParentProductType eq '{product_type}'"
    )

    all_results = []

    if geometry:
        if isinstance(geometry, MultiPolygon):
            # Create one OData filter per polygon, then join with ' or '
            polygons_filters = [
                f" and OData.CSC.Intersects(area=geography'SRID=4326;{poly.wkt}')"
                for poly in geometry.geoms
            ]
        elif isinstance(geometry, Polygon):
            polygons_filters = [
                f" and OData.CSC.Intersects(area=geography'SRID=4326;{geometry.wkt}')"
            ]
        else:
            raise TypeError("Provided geometry must be Polygon or Multipolygon")

    for poly_wkt in polygons_filters:
        query = base_query + poly_wkt + "&$orderby=ContentDate/Start desc&$top=1000"
        url = f"{base_url}?{query}"
        r = requests.get(url)
        r.raise_for_status()
        all_results.extend(r.json().get("value", []))

    return all_results


@log_timing
def query_cdse_for_bursts_in_period(
    start_dt: datetime,
    end_dt: datetime,
    chunk_query_minutes: int = 5,
    geometry: Optional[Polygon | MultiPolygon] = None,
    query_overlap_seconds: int = 5,
    product_type: ValidBurstProducts = "IW_SLC__1S",
    burst_prefix: str = "t",
    lowercase: bool = True,
    max_workers: int = 5,
    output_path: Optional[str] = None,  # <-- new parameter
):
    """
    Parallel, chunked CDSE burst query.
    """

    logging.info(f"Querying CDSE for bursts between : {start_dt} and {end_dt}")

    base_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Bursts"

    chunk = timedelta(minutes=chunk_query_minutes)
    overlap = timedelta(seconds=query_overlap_seconds)

    # -------- Build chunk list --------
    query_dt_chunks = []
    query_start_dt = start_dt

    while query_start_dt <= end_dt:
        query_end_dt = min(query_start_dt + chunk, end_dt)
        query_dt_chunks.append((query_start_dt, query_end_dt))
        if query_end_dt == end_dt:
            break
        query_start_dt = query_end_dt - overlap  # maintain overlap

    if isinstance(geometry, MultiPolygon):
        n_polygons = len(geometry.geoms)
        logging.info(
            f"WARNING : Provided geometry is a MultiPolygon (N polygons = {n_polygons}). "
            f"A separate query will be made for each Polygon within the MultiPolygon. "
            f"Simplify if possible and ensure Polygons are not overlapping."
        )
    else:
        n_polygons = 1

    logging.info(
        f"Separating query into {chunk_query_minutes} "
        f"minute chunks with {query_overlap_seconds} second overlap "
        f"(odata API limits to 1000 responses per request)"
    )
    logging.info(
        f"{len(query_dt_chunks*n_polygons)} chunked queries will be made in parallel with {max_workers} workers"
    )

    burst_product_dict = {}

    # -------- Parallel requests --------
    with ThreadPoolExecutor(max_workers=max_workers) as ex:
        futures = {
            ex.submit(
                _make_chunk_request,
                base_url,
                query_start_dt,
                query_end_dt,
                product_type,
                geometry,
            ): (query_start_dt, query_end_dt)
            for (query_start_dt, query_end_dt) in query_dt_chunks
        }

        for fut in tqdm(
            as_completed(futures), total=len(futures), desc="Querying CDSE for bursts"
        ):
            query_start_dt, query_end_dt = futures[fut]
            try:
                results = fut.result()
            except Exception as err:
                logging.error(f"Chunk {query_end_dt} → {query_start_dt} failed: {err}")
                continue

            # Process results
            if len(results) > 1000:
                logging.info(
                    "WARNING - more than the limit of 1000 results were found for the query."
                    f" Reduce `chunk_query_minutes` to be less than the current value of {5}"
                    f" as some bursts may be missed"
                )
            for b in results:
                track_number = int(b.get("RelativeOrbitNumber"))
                esa_burst_id = int(b.get("BurstId"))
                subswath = b.get("SwathIdentifier")

                burst_id_asf = (
                    f"{burst_prefix}{track_number:03d}_{esa_burst_id:06d}_{subswath}"
                )
                burst_id_asf = burst_id_asf.lower() if lowercase else burst_id_asf

                az_time = datetime.strptime(
                    b.get("AzimuthTime"), "%Y-%m-%dT%H:%M:%S.%fZ"
                )

                # set the key to be a tuple of the burst_id and azimuth time
                # bursts repeat every 6/12 days so the time ensures uniqueness
                if (burst_id_asf, az_time) not in burst_product_dict:
                    burst_product_dict[(burst_id_asf, az_time)] = {
                        "burst_id": burst_id_asf,
                        "burst_id_cdse": b.get("Name"),
                        "scene_id": b.get("ParentProductName").replace(".SAFE", ""),
                        "azimuth_time": az_time,
                        "platform": b.get("PlatformSerialIdentifier"),
                    }

    if not burst_product_dict:
        logging.info("No bursts found for the given time/geometry window.")
    else:
        logging.info(
            f"{len(burst_product_dict)} bursts found for the given time/geometry window.."
        )

    if output_path:
        df = pd.DataFrame.from_dict(burst_product_dict, orient="index")
        df.to_parquet(output_path, index=False)
        logging.info(f"Results written to {output_path}")

    return burst_product_dict


def query_stac_for_metadata_in_period(
    start_dt: datetime,
    end_dt: datetime,
    geometry: Polygon | MultiPolygon | None,
    collections: list,
    stac_catalog: str,
    query: dict | None = None,
):
    """Query A given STAC API for product metadata that falls within the
    provided time range and geometry.

    Parameters
    ----------
    start_dt : datetime
        search start datetime
    end_dt : datetime
        search end datetime
    geometry : shape | Polygon | MultiPolygon | None
        search geometry
    collections : list, optional
        Collection to search, e.g. ["sentinel-1-slc"]
    stac_catalog : str, optional
        STAC catalog url to search, e.g. "https://stac.dataspace.copernicus.eu/v1/"
        or "https://explorer.dea.ga.gov.au/stac"
    query : str, optional
        Additional filtering for the products. e.g.
        {"sar:instrument_mode": {"eq": "IW"}}


    Returns
    -------
    tuple (int, dict)
        Count of matching products and dictionary of metadata for the scenes
        matching the criteria.
    """

    stac_client = pystac_client.Client.open(stac_catalog)
    configure_s3_access(cloud_defaults=True, aws_unsigned=True)
    stac_start_dt = _format_dt(start_dt)
    stac_end_dt = _format_dt(end_dt)
    stac_items = stac_client.search(
        collections=collections,
        datetime=f"{stac_start_dt}/{stac_end_dt}",
        intersects=geometry,
        query=query,
    )
    n_stac_items = stac_items.matched()

    return n_stac_items, stac_items


def load_geojson_as_shape(url: str) -> MultiPolygon:
    """
    Load a GeoJSON from a URL (or local file) and return a flattened MultiPolygon.

    Handles GeoJSONs containing:
    - Polygon features
    - MultiPolygon features
    - Mix of both

    Parameters
    ----------
    url : str
        URL or local path to the GeoJSON.

    Returns
    -------
    MultiPolygon
        Flattened MultiPolygon containing all polygons from the GeoJSON.
    """

    # Load GeoJSON (supports URL or local file)
    if url.startswith("http://") or url.startswith("https://"):
        resp = requests.get(url)
        resp.raise_for_status()
        geojson = resp.json()
    else:
        import json

        with open(url, "r") as f:
            geojson = json.load(f)

    # Collect all geometries
    geometries = []

    features = geojson.get("features", [])
    for feat in features:
        geom = shape(feat["geometry"])
        if isinstance(geom, Polygon):
            geometries.append(geom)
        elif isinstance(geom, MultiPolygon):
            geometries.extend(geom.geoms)
        else:
            raise ValueError(f"Unexpected geometry type: {type(geom)}")

    if not geometries:
        raise ValueError("No Polygon/MultiPolygon geometries found in GeoJSON.")

    # Return a single flattened MultiPolygon
    return MultiPolygon(geometries)


def make_burst_product_completeness_report(
    s3_report_folder: str,
    s3_bucket: str,
    s3_project_folder: str,
    collection_number: str,
    start_dt: datetime,
    end_dt: datetime,
    geometry: str | None,
    stac_catalog: str,
    identify_missing_linked_static_layers: bool = True,
    dem_type: ValidDemType = "best",
    static_layer_validity_start_date=20140403,
    linked_static_layer_s3_bucket: str | None = None,
    linked_static_layer_s3_project_folder: str | None = None,
    linked_static_layer_collection_number: str | None = None,
):
    """For variable descriptions see the cli:
    sar_pipeline/pipelines/isce3_rtc/monitoring/cli.py
    """

    logging.info(f"Running Sentinel-1 IW NRB completeness check")

    if dem_type not in VALID_DEMS:
        raise ValueError(
            f"Invalid dem_type {dem_type}. dem_type valid values are {VALID_DEMS}"
        )

    report_dt = datetime.now()
    # format for completeness report -> "{report_dt}_{start_dt}_{end_dt}_completeness_report.json"

    completeness_report_name = (
        f"{report_dt.strftime('%Y%m%dT%H%M%S')}"
        f"_{start_dt.strftime('%Y%m%dT%H%M%S')}"
        f"_{end_dt.strftime('%Y%m%dT%H%M%S')}"
        "_completeness_report.json"
    )

    if isinstance(geometry, str):
        geometry = load_geojson_as_shape(geometry).simplify(tolerance=0.1)

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
        end_dt=end_dt - buffer,
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
    for i in range(0, 1):
        for burst_product in tqdm(
            stac_items.items_as_dicts(),
            total=n_stac_matches,
            desc="Iterating STAC items",
        ):
            # logging.info(burst_product)
            odc_id = burst_product["id"]
            burst_id = burst_product["properties"]["sarard:burst_id"]
            azimuth_time = burst_product["properties"]["datetime"]
            created_time = burst_product["properties"]["created"]
            # convert dts
            azimuth_time = datetime.strptime(azimuth_time, "%Y-%m-%dT%H:%M:%S.%fZ")
            created_time = datetime.strptime(created_time, "%Y-%m-%dT%H:%M:%S.%fZ")

            if (burst_id, azimuth_time) not in expected_burst_product_dict:
                # additional product that is in the list of bursts from the CDSE.
                # We have picked up with the expanded time buffer
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
                burst_products_indexed[(burst_id, azimuth_time)][
                    "created"
                ] = created_time

            # we are dealing with a duplicate item
            else:

                n_duplicate_products_to_archive += 1

                # create a list of the duplicate products for a given burst
                if (burst_id, azimuth_time) not in duplicate_products_to_archive:
                    duplicate_products_to_archive[(burst_id, azimuth_time)] = []

                # get the created date of the product already in the index list
                _existing_created_time = burst_products_indexed[
                    (burst_id, azimuth_time)
                ]["created"]

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
            logging.info("Query the CDSE STAC API for scene metadata")
            # stac query STAC for items with slight buffer in times
            buffer = timedelta(minutes=10)
            n_stac_matches, stac_items = query_stac_for_metadata_in_period(
                start_dt=start_dt - buffer,
                end_dt=end_dt - buffer,
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
            # we need to use the scenes to determine which DEM is used for the
            # missing static layers
            for scene in tqdm(
                scenes_to_process,
                desc="Identifying missing static layers for unprocessed scenes",
            ):

                scene_poly = shape(scene_dict[scene].geometry)

                # check if the scene crosses the antimeridian
                if check_shape_crosses_antimeridian(scene_poly):
                    scene_bounds = get_bounds_for_antimeridian_shape(scene_poly)
                else:
                    scene_bounds = scene_poly.bounds

                # get the best dem for processing if required
                if dem_type == "best":
                    burst_dem_type = get_best_dem_type_for_scene(scene_bounds)

                # get the list of bursts that belong to that scene
                scene_bursts = [
                    k
                    for k, v in expected_burst_product_dict.items()
                    if v["scene_id"] == scene
                ]

                # iterate through the burst ids
                for burst_id, azimuth_time in scene_bursts:

                    # construct the s3_prefix for the static layer
                    expected_static_layer_s3_product_folder = make_rtc_s1_static_product_s3_prefix(
                        s3_project_folder=linked_static_layer_s3_project_folder,
                        collection_number=linked_static_layer_collection_number,
                        dem_type=burst_dem_type,
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

    # get the counts of the missing static layers
    n_bursts_missing_static_layers = len(bursts_missing_static_layers)
    n_scenes_missing_static_layers = len(scenes_missing_static_layers)

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
        "s3_bucket": s3_bucket,
        "s3_project_folder": s3_project_folder,
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
    completeness_json = make_completeness_report_json_safe(completeness_dict)

    os.makedirs("TMP", exist_ok=True)
    with open(f"TMP/{completeness_report_name}", "w") as f:
        json.dump(completeness_json, f, indent=2)

    # upload the completeness report to the desired AWS S3 bucket
    s3_uploder = S3Util()
    s3_uploder.upload_file(
        s3_bucket,
        Path(s3_report_folder) / completeness_report_name,
        f"TMP/{completeness_report_name}",
    )


if __name__ == "__main__":

    s3_bucket = "deant-data-public-dev"
    s3_report_folder = "TMP/completeness_reports"
    collection_number = 0
    stac_catalog = "https://explorer.dev.dea.ga.gov.au/stac"
    # start_dt = datetime(2025, 1, 20, 12, 0, 0)
    # end_dt = datetime(2025, 1, 21, 0, 0, 0)
    # start_dt = datetime(2025, 6, 27, 20, 40, 0) # ant test
    # end_dt = datetime(2025, 6, 27, 20, 50, 0) # ant test
    start_dt = datetime(2024, 12, 15, 12, 0, 0)  # ant test
    end_dt = datetime(2024, 12, 16, 0, 0, 0)  # ant test
    # Aus
    shape_url = "https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/persistent/DEA-non-offshore-product-extent.geojson"
    s3_project_folder = "experimental/for_zhengshu"
    # Ant
    shape_url = "https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/persistent/antarctica_roi_4326.geojson"
    s3_project_folder = "experimental/baseline/antarctica"
    identify_missing_linked_static_layers = True
    dem_type = "best"
    static_layer_validity_start_date = 20140403
    linked_static_layer_s3_project_folder = s3_project_folder
    linked_static_layer_s3_bucket = s3_bucket
    linked_static_layer_collection_number = collection_number

    # where to send messages
    # index_sqs_queue_url = ""
    # nrb_process_sqs_queue_url = ""
    # static_layer_process_sqs_queue_url = ""

    make_burst_product_completeness_report(
        s3_report_folder=s3_report_folder,
        s3_bucket=s3_bucket,
        s3_project_folder=s3_project_folder,
        collection_number=collection_number,
        start_dt=start_dt,
        end_dt=end_dt,
        geometry=shape_url,
        stac_catalog=stac_catalog,
        identify_missing_linked_static_layers=True,
        dem_type="best",
        static_layer_validity_start_date=20140403,
        linked_static_layer_s3_bucket=linked_static_layer_s3_bucket,
        linked_static_layer_s3_project_folder=linked_static_layer_s3_project_folder,
        linked_static_layer_collection_number=linked_static_layer_collection_number,
    )
