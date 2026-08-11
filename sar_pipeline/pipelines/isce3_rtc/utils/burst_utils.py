import asf_search
from datetime import datetime, timedelta
import logging
import os
import shapely
from pathlib import Path
from shapely.geometry import Polygon, MultiPolygon
from typing import Optional, Literal
import sys
import requests
import zipfile
import xml.etree.ElementTree as ET
from concurrent.futures import ThreadPoolExecutor, as_completed
from tqdm import tqdm
import pandas as pd
import s1reader

from sar_pipeline.utils.general import log_timing, format_dt_utc
from sar_pipeline.utils.aws import find_s3_filepaths_from_suffixes
from sar_pipeline.utils.dem import ValidDemType
from sar_pipeline.utils.sentinel1 import get_polarisation_list_from_scene_id
from sar_pipeline.pipelines.isce3_rtc.metadata.filetypes import REQUIRED_ASSET_FILETYPES
from sar_pipeline.pipelines.isce3_rtc.metadata.odc import (
    make_rtc_s1_product_s3_prefix,
    make_rtc_s1_static_product_s3_prefix,
)
from sar_pipeline.preparation.downloads.scenes import (
    query_scene_from_asf,
    query_scene_from_cdse,
    NonSingleSceneResultError,
)
from sar_pipeline.utils.sentinel1 import get_dates_from_scene_id

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ValidBurstProducts = Literal["IW_SLC__1S", "EW_SLC__1S"]


def get_burst_info_for_scene_from_asf(
    scene: str, burst_prefix: str = "t", lowercase: bool = True
) -> dict[str, dict[str, str | datetime | shapely.geometry.Polygon]]:
    """Get the burst ids, start time, azimuth_time, end_time, polarisations and
    geometries for a scene from ASF. Return as a dictionary of bursts as the keys,
    and times, polarisations and geometries as sub-dictionaries. Warning - the end_time
    returned from the ASF API is different than that returned from the CDSE API.

    Warning - Only IW Bursts Available

    Parameters
    ----------
    scene : str
        the scene id. e.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD
    burst_prefix : str
        A prefix to add to the burst string. default 't'. For example:
        070_149822_IW3 -> t070_149822_IW3 with burst_prefix = 't'.
    lowercase: bool
        convert the burst to lowercase. default to True to match workflow output.

    Raises
    -------
    FileExistsError:
        The scene does not exist on the ASF.

    Returns
    -------
    dict
        unique dict of scene burst ids mapped to the azimuth start time,
        start time, end time, geometry and list of polarisations.
        {
            't070_149822_IW3' :
                {
                    azimuth_time : datetime.datetime,
                    start_time : datetime.datetime,
                    end_time : datetime.datetime,
                    geometry: shapely.geometry
                    pols: list[str]
            },
            ...
        }
    """

    st, et = get_dates_from_scene_id(scene)

    results = asf_search.search(
        platform=[asf_search.PLATFORM.SENTINEL1],
        maxResults=100,
        processingLevel="BURST",
        start=st - timedelta(seconds=2),
        end=et + timedelta(seconds=2),
    )

    burst_info = {}

    for b in results:
        if scene in b.properties["url"]:
            burst_id = f"{burst_prefix}{b.properties['burst']['fullBurstID']}"
            burst_id = burst_id.lower() if lowercase else burst_id
            # get start and end times referenced in metadata
            burst_st = datetime.strptime(
                b.properties["startTime"], "%Y-%m-%dT%H:%M:%SZ"
            )
            # WARNING - the end time differs that the CDSE end time
            burst_et = datetime.strptime(b.properties["stopTime"], "%Y-%m-%dT%H:%M:%SZ")
            # get the azimuth time. This is the start time referenced by s1_reader
            burst_azimuth_st = datetime.strptime(
                b.properties["burst"]["azimuthTime"], "%Y-%m-%dT%H:%M:%SZ"
            )
            burst_geom = shapely.geometry.shape(b.geometry)
            pol = b.properties["polarization"].upper()
            if burst_id not in burst_info:
                burst_info[burst_id] = {
                    "azimuth_time": burst_azimuth_st,
                    "start_time": burst_st,
                    "end_time": burst_et,
                    "geometry": burst_geom,
                    "pols": [pol],
                }
            elif burst_id in burst_info and pol not in burst_info[burst_id]["pols"]:
                burst_info[burst_id]["pols"].append(pol)

    if len(burst_info) == 0:
        raise FileExistsError(
            "No burst id's for scene could be found on the ASF. Ensure input values are correct "
            "or set `--scene_data_source CDSE` as recent scenes may not be available on ASF, or the scene is missing"
        )

    return burst_info


def get_burst_info_for_scene_from_cdse(
    scene: str, burst_prefix: str = "t", lowercase: bool = True
) -> dict[str, dict[str, str | datetime | shapely.geometry.Polygon]]:
    """Get the burst ids, start time, azimuth_time, end_time, polarisations and
    geometries for a scene from ASF. Return as a dictionary of bursts as the keys,
    and times, polarisations and geometries as sub-dictionaries. Warning - the end_time
    returned from the CDSE API is different than that returned from the ASF API

    Parameters
    ----------
    scene : str
        the scene id. e.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD
    burst_prefix : str
        A prefix to add to the burst string. default 't'. For example:
        070_149822_IW3 -> t070_149822_IW3 with burst_prefix = 't'.
    lowercase: bool
        convert the burst to lowercase. default to True to match workflow output.

    Raises
    -------
    FileExistsError:
        The scene does not exist on the CDSE.

    Returns
    -------
    dict
        unique dict of scene burst ids mapped to the azimuth start time,
        start time, geometry and list of polarisations.
        {
            't070_149822_IW3' :
                {
                    azimuth_time : datetime.datetime,
                    start_time : datetime.datetime,
                    end_time : datetime.datetime,
                    geometry: shapely.geometry
                    pols: list[str]
            },
            ...
        }
    """

    base_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Bursts"
    # one products per burst+pol, set this value high to be safe.
    query = f"$filter=ParentProductName eq '{scene}.SAFE'&$top=500"
    url = f"{base_url}?{query}"

    response = requests.get(url)
    response.raise_for_status()  # Raise error for bad responses

    results = response.json().get("value", [])
    burst_info = {}

    for b in results:
        track_number = int(b.get("RelativeOrbitNumber"))
        esa_burst_id = int(b.get("BurstId"))
        subswath = b.get("SwathIdentifier")
        # construct the unique JPL burst id
        # defined here - https://github.com/isce-framework/s1-reader/blob/main/src/s1reader/s1_burst_id.py#L133
        burst_id = f"{burst_prefix}{track_number:03d}_{esa_burst_id:06d}_{subswath}"
        burst_id = burst_id.lower() if lowercase else burst_id
        # get start-times, end-times and geometries
        burst_st = datetime.strptime(
            b.get("BeginningDateTime"), "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        # WARNING - the end time differs that the ASF end time
        burst_et = datetime.strptime(b.get("EndingDateTime"), "%Y-%m-%dT%H:%M:%S.%fZ")
        # get the azimuth start time. This is the start time referenced by s1_reader
        burst_azimuth_st = datetime.strptime(
            b.get("AzimuthTime"), "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        burst_geom = shapely.geometry.shape(b.get("GeoFootprint"))
        pol = b.get("PolarisationChannels").upper()

        if burst_id not in burst_info:
            burst_info[burst_id] = {
                "azimuth_time": burst_azimuth_st,
                "start_time": burst_st,
                "end_time": burst_et,
                "geometry": burst_geom,
                "pols": [pol],
            }
        elif burst_id in burst_info and pol not in burst_info[burst_id]["pols"]:
            burst_info[burst_id]["pols"].append(pol)

    if len(burst_info) == 0:
        raise FileExistsError(
            "No burst ids for scene could be found on the CDSE. Ensure input values are correct. "
            f"Input scene : {scene}"
        )

    return burst_info


def check_burst_product_h5_exists_in_s3(
    product: Literal["RTC_S1", "RTC_S1_STATIC"],
    burst_id_list: list[str],
    burst_st_list: list[str],
    burst_polarisations: list[str],
    s3_bucket: str,
    s3_project_folder: str,
    collection_number: int,
    dem_type: ValidDemType,
    static_layer_validity_start_date: int,
    make_existing_products: bool = False,
    early_exit: bool = True,
    early_exit_code: int = 100,
) -> tuple[list[str], list[str]]:
    """Check if the product already exists in s3. The storage location differs
    for static layers (RTC_S1_STATIC) and backscatter (RTC_S1). This function checks
    to see if a .h5 file exists for the given product in s3.

    Parameters
    ----------
    product : str
        Product being created, either 'RTC_S1' or 'RTC_S1_STATIC'
    burst_id_list : list[str]
        List of burst ids
    burst_st_list : list[str]
        List of start-times corresponding to each burst id
    s3_bucket : str
        The bucket where the products are stored
    s3_project_folder : str
        The subpath within the bucket
    collection_number : int
        The collection_number as an int.
    dem_type : str, ValidDemType
        The dem type used for processing.
    static_layer_validity_start_date : int
        The validity start date for the static layers used in processing,
        expressed in YYYYMMDD format.
    make_existing_products : bool
        whether to make products if they already exist in s3. If False,
        process will exit early if all already exist. Default is False.
    early_exit : bool,
        Exit the process early with a 100 error code if True. If false,
        No error is raised.
    early_exit_code : int
        If early exit, the code to exit the program with. default 100.

    Returns
    -------
    tuple(list,list)
        0: List of burst ids where products already exist
            e.g. ['t028_059508_iw1','t028_059507_iw2' ...]
        1: List of s3 paths corresponding to existing products.
    """

    existing_burst_ids = []
    existing_s3_paths = []

    for burst_id, burst_st in zip(burst_id_list, burst_st_list):
        # get the path to search for in s3

        acquisition_mode = burst_id.split("_")[-1][0:2]  # iw / ew

        if product == "RTC_S1_STATIC":
            s3_product_subpath = make_rtc_s1_static_product_s3_prefix(
                s3_project_folder=s3_project_folder,
                collection_number=collection_number,
                burst_id=burst_id,
                dem_type=dem_type,
                static_layer_validity_start_date=static_layer_validity_start_date,
                acquisition_mode=acquisition_mode,
            )
        if product == "RTC_S1":
            s3_product_subpath = make_rtc_s1_product_s3_prefix(
                s3_project_folder=s3_project_folder,
                collection_number=collection_number,
                burst_polarisations=burst_polarisations,
                burst_id=burst_id,
                burst_st=burst_st,
                acquisition_mode=acquisition_mode,
            )
        # assume the product exists if there is a .h5 file
        logging.info(f"searching s3 folder : {s3_product_subpath}")
        product_h5_files = find_s3_filepaths_from_suffixes(
            bucket_name=s3_bucket, s3_folder=s3_product_subpath, suffixes=[".h5"]
        )
        if len(product_h5_files[".h5"]) > 0:
            existing_burst_ids.append(burst_id)
            existing_s3_paths.append(s3_product_subpath)

    if len(existing_burst_ids) > 0:
        logging.warning(
            f"Products already exist for {len(existing_burst_ids)} of {len(burst_id_list)} requested bursts:"
        )
        # iterate through existing products and show message with path
        for i in range(0, len(existing_burst_ids)):
            logger.warning(
                f"Existing product : {existing_burst_ids[i]}, s3_path : {s3_bucket}/{existing_s3_paths[i]}"
            )
        if not make_existing_products:
            # limit burst ids to those which haven't been processed
            burst_id_list_to_process = [
                b for b in burst_id_list if b not in existing_burst_ids
            ]
            logger.warning(
                "Skipping the existing products. To create these, remove the existing products from S3. OR, pass flag "
                "'--make-existing-products' to workflow. WARNING this can create duplicates that may impact downstream processes."
            )
            # exit if all existing burst products exist
            if all(b in existing_burst_ids for b in burst_id_list):
                logging.warning("All desired burst products already exist.")
                if early_exit:
                    logging.warning("Exiting process early")
                    sys.exit(early_exit_code)
        else:
            burst_id_list_to_process = burst_id_list
            logger.warning(
                "Existing products are being re-created. WARNING This will create duplicates in the S3 bucket that may impact downstream processes. "
                "set '--make-existing-products' if this behavior is not desired."
            )
    else:
        logger.info(f"No products already exist for the requested bursts.")
        burst_id_list_to_process = burst_id_list

    # return the list of bursts that need to be processed
    return burst_id_list_to_process


def ensure_static_layers_in_s3(
    scene: str,
    burst_id_list,
    static_layers_s3_bucket: str,
    static_layers_collection_number: int,
    static_layers_s3_project_folder: str,
    dem_type: ValidDemType,
    static_layer_validity_start_date: int,
    early_exit_code: int = 101,
):
    """Check AWS S3 bucket to ensure static layers exist for the required bursts

    Parameters
    ----------
    scene : str
        the scene id. e.g. S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD
    burst_id_list : list
        List of specific bursts to see if static layers exist.
    static_layers_s3_bucket : str
        s3 bucket
    static_layers_collection_number : int
        collection number of the static layers
    static_layers_s3_project_folder : str
        project folder for static layers
    dem_type : str, ValidDemType
        The dem type used for processing.
    static_layer_validity_start_date : int
        The validity start date for the static layers used in processing,
        expressed in YYYYMMDD format.
    early_exit_code:
        The exit code to quit the process with if static layers don't exist.

    Returns
    -------
    bool
        True if all required static layer files exist.

    Raises
    ------
    FileExistsError
        If any of the required static layer files are missing for a burst.
    """

    if not burst_id_list:
        raise ValueError("A list of bursts for scene must be passed in.")

    n_bursts = len(burst_id_list)
    raise_missing_file_error = False
    missing_burst_files = {}

    for burst_id in burst_id_list:

        acquisition_mode = burst_id.split("_")[-1][0:2]  # iw / ew

        static_layers_s3_folder = make_rtc_s1_static_product_s3_prefix(
            static_layers_s3_project_folder,
            static_layers_collection_number,
            dem_type=dem_type,
            static_layer_validity_start_date=static_layer_validity_start_date,
            burst_id=burst_id,
            acquisition_mode=acquisition_mode,
        )
        filetype_to_s3paths = find_s3_filepaths_from_suffixes(
            static_layers_s3_bucket,
            static_layers_s3_folder,
            suffixes=REQUIRED_ASSET_FILETYPES["RTC_S1_STATIC"],
        )
        # find the filetypes that are missing from the static layer folder
        missing_burst_files[burst_id] = [
            filetype
            for filetype, s3paths in filetype_to_s3paths.items()
            if len(s3paths) == 0
        ]
        if len(missing_burst_files[burst_id]) > 0:
            # we have a burst missing files, flag to raise an error below
            raise_missing_file_error = True

    if not raise_missing_file_error:
        logger.info(
            f"All {n_bursts} of {n_bursts} required static layers exist for bursts in scene : {scene}"
        )
        return True
    else:
        n_missing = len(
            [x for x in missing_burst_files if len(missing_burst_files[x]) > 0]
        )
        missing_info = "\n".join(
            f" Burst ID: {burst_id} -> Missing Filetypes: {', '.join(missing_files)}"
            for burst_id, missing_files in missing_burst_files.items()
            if missing_files  # only include bursts with missing files
        )
        logger.error(
            f"\nMissing static layers for bursts in scene : {scene}\n"
            f"{n_missing} of {n_bursts} bursts being processed have files missing.\n"
            f"Missing Bursts and static layer filetypes:\n"
            f"{missing_info}\n"
            f"Example AWS S3 path searched : {static_layers_s3_bucket}/{static_layers_s3_folder}\n"
            f"Check linked location arguments or create the missing static layers. "
            f"E.g. re-run the workflow using `--product RTC_S1_STATIC`\n"
            f"See workflow docs for details at docs/pipelines/isce3-rtc.md."
        )
        sys.exit(early_exit_code)


def _make_chunk_cdse_request(
    base_url: str,
    chunk_start: datetime,
    chunk_end: datetime,
    product_type: ValidBurstProducts,
    geometry: Optional[Polygon | MultiPolygon],
):
    """Execute a single GET request for one time chunk."""
    chunk_start = format_dt_utc(chunk_start)
    chunk_end = format_dt_utc(chunk_end)

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
    max_workers: int = 10,
    output_path: Optional[str] = None,  # <-- new parameter
):
    """_summary_

    Parameters
    ----------
    start_dt : datetime
        search start datetime
    end_dt : datetime
        search end datetime
    chunk_query_minutes : int, optional
        request minute chunks, by default 5
    geometry : Optional[Polygon  |  MultiPolygon], optional
        geometry of the region of interest, by default None
    query_overlap_seconds : int, optional
        Overlap seconds for successive queries, by default 5
    product_type : ValidBurstProducts, optional
        Filter for correct operational mode, by default "IW_SLC__1S"
    burst_prefix : str, optional
        prefix for burst_id formatting, by default "t"
    lowercase : bool, optional
        return burst_id in lowercase, by default True
    max_workers : int, optional
        Number of parallel requests to make, by default 10.
    output_path : Optional[str], optional
        path to write the bursts to a parquet, by default None.

    Returns
    -------
    dict
        dictionary with tuple key (burst_id, azimuth_time) and values
        {
            "burst_id": str,
            "burst_id_cdse": str,
            "scene_id": str,
            "azimuth_time": datetime,
            "platform": str,
        }

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
                _make_chunk_cdse_request,
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
                    f" Reduce `chunk_query_minutes` to be less than the current value of "
                    f" {chunk_query_minutes} as some bursts may be missed"
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


def _get_burst_sensing_times_from_annotation(
    scene_path: Path, sensor_mode: str, swath_num: int, pol: str
) -> list[datetime]:
    """Parse the raw radar `sensingTime` for each burst directly from the
    scene's annotation XML, in burst order.

    Each burst in the annotation has both an `azimuthTime` (the zero-Doppler
    azimuth time of the first line, which is what s1reader exposes as
    `Sentinel1BurstSlc.sensing_start`) and a separate `sensingTime` (the raw
    radar sensing time of the first line). s1reader parses `sensingTime`
    internally to compute the burst ID but does not expose it on the
    returned burst object. CDSE's `BeginningDateTime`/`start_time` for a
    burst is populated from `sensingTime`, not `azimuthTime`, so it must be
    read from the annotation directly to get an equivalent value.

    Parameters
    ----------
    scene_path : Path
        Path to the scene .zip or .SAFE directory.
    sensor_mode : str
        Acquisition mode, e.g. "iw" or "ew".
    swath_num : int
        Subswath number.
    pol : str
        Polarization, e.g. "vv".

    Returns
    -------
    list[datetime]
        Sensing times ordered so that index i corresponds to the burst
        with `i_burst == i`, as returned by `s1reader.load_bursts`.
    """

    id_str = f"{sensor_mode}{swath_num}-slc-{pol.lower()}"

    if scene_path.is_dir():
        annotation_dir = scene_path / "annotation"
        matches = [f for f in os.listdir(annotation_dir) if id_str in f]
        if not matches:
            raise ValueError(f"burst {id_str} not in SAFE: {scene_path}")
        tree = ET.parse(annotation_dir / matches[0])
    else:
        with zipfile.ZipFile(scene_path, "r") as z_file:
            matches = [
                f
                for f in z_file.namelist()
                if f.split("/")[-2] == "annotation" and id_str in f.split("/")[-1]
            ]
            if not matches:
                raise ValueError(f"burst {id_str} not in SAFE: {scene_path}")
            with z_file.open(matches[0]) as f:
                tree = ET.parse(f)

    burst_list = tree.find("swathTiming/burstList")
    return [
        datetime.fromisoformat(burst.find("sensingTime").text) for burst in burst_list
    ]


def get_burst_info_and_scene_poly_from_file(
    scene_path: str | Path,
    orbit_path: str | Path,
    swath_list: list[int],
) -> tuple[dict, shapely.geometry.base.BaseGeometry]:
    """
    Load burst metadata and geometry for a Sentinel-1 scene.

    Parameters
    ----------
    scene_path : str or Path
        Path to the scene .zip or .SAFE file.
    orbit_path : str or Path
        Path to the associated orbit file for the scene.
    swath_list : list[int]
        Subswath numbers to load bursts from.

    Returns
    -------
    tuple[dict, shapely.geometry.base.BaseGeometry]
        Dict keyed by burst ID with sensing times, geometry, and
        polarizations, and the unioned scene polygon covering all bursts.
    """

    scene_path = Path(scene_path)
    orbit_path = Path(orbit_path)
    scene_id = scene_path.stem  # strips .zip or .SAFE
    sensor_mode = scene_id.split("_")[1].lower()
    pol = get_polarisation_list_from_scene_id(scene_id)[0]

    logger.info(f"Loading burst info from: {scene_path}")

    all_scene_burst_info = {}
    for swath_num in swath_list:
        bursts = s1reader.load_bursts(
            path=str(scene_path),
            orbit_path=str(orbit_path),
            swath_num=swath_num,
            pol=pol,
        )
        sensing_times = _get_burst_sensing_times_from_annotation(
            scene_path, sensor_mode, swath_num, pol
        )
        for burst in bursts:
            bid = burst.burst_id
            burst_geom = shapely.geometry.shape(burst.border[0])
            entry = all_scene_burst_info.setdefault(
                str(bid),
                {
                    "azimuth_time": burst.sensing_start,
                    "start_time": sensing_times[burst.i_burst],
                    "end_time": burst.sensing_stop,
                    "geometry": burst_geom,
                    "pols": [],
                },
            )
            entry["pols"].append(burst.polarization)

    scene_polygon = shapely.ops.unary_union(
        [b["geometry"] for b in all_scene_burst_info.values()]
    )

    return all_scene_burst_info, scene_polygon


def assert_burst_info_equivalent(
    cdse_burst_info: dict,
    file_burst_info: dict,
    geom_tolerance: float = 1e-3,
    test_geometries=False,
) -> None:
    """
    Helper to Assert burst info from the CDSE API matches burst info loaded
    directly from a SAFE file, for the same burst IDs.

    Parameters
    ----------
    cdse_burst_info : dict
        Output of get_burst_info_for_scene_from_cdse.
    file_burst_info : dict
        Output of get_burst_info_from_scene_file.
    geom_tolerance : float
        Tolerance (degrees) for near-equality of burst geometries, allowing
        for minor coordinate rounding differences between sources.
    """
    assert set(cdse_burst_info.keys()) == set(file_burst_info.keys()), (
        "Burst IDs differ between CDSE and SAFE file: "
        f"cdse only={set(cdse_burst_info) - set(file_burst_info)}, "
        f"file only={set(file_burst_info) - set(cdse_burst_info)}"
    )

    for burst_id, file_entry in file_burst_info.items():
        cdse_entry = cdse_burst_info[burst_id]

        assert (
            file_entry["azimuth_time"] == cdse_entry["azimuth_time"]
        ), f"azimuth_time mismatch for burst {burst_id}"
        assert (
            file_entry["start_time"] == cdse_entry["start_time"]
        ), f"start_time mismatch for burst {burst_id}"
        # end_time intentionally not compared: get_burst_info_for_scene_from_cdse's
        # docstring warns the CDSE end_time convention differs from other sources.

        if test_geometries:
            # The geometries are different, and hard to compare
            assert file_entry["geometry"].equals_exact(
                cdse_entry["geometry"], tolerance=geom_tolerance
            ), f"geometry mismatch for burst {burst_id}"

        # get_burst_info_from_scene_file only loads a single polarisation,
        # so just confirm it's among the polarisations CDSE reports
        for pol in file_entry["pols"]:
            assert (
                pol in cdse_entry["pols"]
            ), f"pol {pol} for burst {burst_id} not in CDSE pols {cdse_entry['pols']}"


def get_burst_info_and_scene_poly_from_api(
    scene: str,
    sensor_mode: str,
) -> tuple[shapely.geometry.base.BaseGeometry, str, dict, dict]:
    """Query CDSE (falling back to ASF) for scene-level metadata, and CDSE
    for burst-level metadata, for a scene that has not been downloaded
    locally.

    Parameters
    ----------
    scene : str
        The scene id, e.g.
        S1A_IW_SLC__1SDV_20200511T135117_20200511T135144_032518_03C421_7768
    sensor_mode : str
        Sensor acquisition mode extracted from the scene id, e.g. "IW" or
        "EW". Only used to tailor the error message if no scene is found.

    Returns
    -------
    scene_polygon : shapely.geometry.base.BaseGeometry
        The scene's footprint geometry.
    metadata_src : str
        "CDSE" or "ASF", whichever source the scene was found on.
    scene_metadata : dict
        The raw metadata for the found scene.
    all_scene_burst_info : dict
        Output of get_burst_info_for_scene_from_cdse.

    Raises
    ------
    NonSingleSceneResultError
        If not exactly one scene is found on CDSE or ASF.
    """

    logger.info(f"Searching CDSE for scene metadata : {scene}")
    try:
        scene_results, metadata_src = query_scene_from_cdse(scene), "CDSE"
    except Exception as e:
        logger.error(f"CDSE Query failed. Error : {e}")
        logger.info(f"Falling back to ASF search for scene metadata : {scene}")
        logger.warning("ASF may not have the most recent data available from the CDSE")
        scene_results, metadata_src = query_scene_from_asf(scene), "ASF"

    if len(scene_results) != 1:
        msg = (
            f"Expected 1 scene, found {len(scene_results)} results for scene id : "
            f"{scene}. Check input scene."
        )
        if sensor_mode == "EW":
            msg += (
                " An EW SLC was passed. If this was created from L0 data the "
                "`scene_path` to a local file or remote URL to download must be "
                "passed directly as scene does not exist on the CDSE/ASF."
            )
        raise NonSingleSceneResultError(msg)

    logger.info(f"Scene metadata successfully retrieved from {metadata_src}")
    scene_metadata = scene_results[0]
    if metadata_src == "CDSE":
        scene_polygon = shapely.geometry.shape(scene_metadata["GeoFootprint"])
    else:
        scene_polygon = shapely.geometry.shape(scene_metadata.geometry)

    logger.info(f"The original scene shape is : {scene_polygon}")
    logger.info(f"The original scene bounds are : {scene_polygon.bounds}")

    logger.info("Querying CDSE for scene burst ids and metadata")
    all_scene_burst_info = get_burst_info_for_scene_from_cdse(scene)
    logger.info(f"{len(all_scene_burst_info)} burst ids found for scene from CDSE API")

    return all_scene_burst_info, scene_polygon
