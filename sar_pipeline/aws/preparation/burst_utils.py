import asf_search
from datetime import datetime, timedelta
import boto3
from botocore import UNSIGNED
from botocore.config import Config
import os
import logging
import shapely
from typing import Literal
import sys
import requests

from sar_pipeline.aws.metadata.filetypes import REQUIRED_ASSET_FILETYPES
from sar_pipeline.aws.metadata.odc import (
    make_rtc_s1_s3_subpath,
    make_rtc_s1_static_s3_subpath,
)
from sar_pipeline.nci.preparation.scenes import parse_scene_file_dates

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_aws_environment_credentials() -> list[str]:
    """Checks if the required credentials exist

    Returns: list
        A list of the credentials that are missing
    """
    # search for credentials in environment and raise warning if not there
    MISSING_CREDENTIALS = []
    if os.environ.get("AWS_ACCESS_KEY_ID") is None:
        wrn_msg = "AWS_ACCESS_KEY_ID is not set in environment variables. Set if authentication required on bucket"
        logging.warning(wrn_msg)
        MISSING_CREDENTIALS.append("AWS_ACCESS_KEY_ID")
    if os.environ.get("AWS_SECRET_ACCESS_KEY") is None:
        wrn_msg = "AWS_SECRET_ACCESS_KEY is not set in environment variables. Set if authentication required on bucket"
        logging.warning(wrn_msg)
        MISSING_CREDENTIALS.append("AWS_SECRET_ACCESS_KEY")
    if os.environ.get("AWS_DEFAULT_REGION") is None:
        wrn_msg = "AWS_DEFAULT_REGION is not set in environment variables. Set if authentication required on bucket"
        logging.warning(wrn_msg)
        MISSING_CREDENTIALS.append("AWS_DEFAULT_REGION")
    return MISSING_CREDENTIALS


def find_s3_filepaths_from_suffixes(bucket_name, s3_folder, suffixes) -> dict:
    """Search a folder within an s3 bucket for files

    Parameters
    ----------
    bucket_name : str
        S3 bucket
    s3_folder : str
        Folder within the bucket
    suffixes : list
        List of suffixes, or endswiths to search for. For example
        ['.png','.tif'] to find files which end with .png and .tif respectively

    Returns
    -------
    dict
        Dictionary relating the suffix in the list provided to a list of
        files in the bucket and folder. E.g.
        {
            '.png' : ['bucket_name/s3_folder/cat.png','bucket_name/s3_folder/dog.png'],
            '.tif' : ['bucket_name/s3_folder/red.tif','bucket_name/s3_folder/blue.tif']
        }
    """

    MISSING_CREDENTIALS = check_aws_environment_credentials()
    if MISSING_CREDENTIALS:
        # attempt to connect without authentication
        logger.info(
            f"Attempting to search bucket without complete credentials. Missing credentials : {MISSING_CREDENTIALS}"
        )
        s3 = boto3.client("s3", config=Config(signature_version=UNSIGNED))
    else:
        s3 = boto3.client("s3")

    response = s3.list_objects_v2(Bucket=bucket_name, Prefix=s3_folder)
    if "Contents" not in response:
        # folder does not exist, all required files missing
        return {s: [] for s in suffixes}

    # Extract filenames from S3 keys
    existing_files = [obj["Key"] for obj in response["Contents"]]

    # Check if all required suffixes have at least one match
    suffix_to_s3path = {}
    for s in suffixes:
        suffix_to_s3path[s] = [f for f in existing_files if f.endswith(s)]

    return suffix_to_s3path


def get_burst_info_for_scene_from_asf(
    scene: str, burst_prefix: str = "t", lowercase: bool = True
) -> dict[str, dict[str, str | datetime | shapely.geometry.Polygon]]:
    """Get the burst ids, start-times, polarisations and geometries for a scene from ASF.
    Return as a dictionary of bursts as the keys, and start-times, polarisations and geometries as
    sub-dictionaries.

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
        unique dict of scene burst ids mapped to start_times, geometries and shapes
        {'t070_149822_IW3' : {start_time : datetime.datetime, geometry: shapely.geometry}}
    """

    st, et = parse_scene_file_dates(scene)

    results = asf_search.search(
        platform=[asf_search.PLATFORM.SENTINEL1],
        maxResults=100,
        processingLevel="BURST",
        start=st - timedelta(seconds=1),
        end=et + timedelta(seconds=1),
    )

    burst_info = {}

    for b in results:
        if scene in b.properties["url"]:
            burst_id = f"{burst_prefix}{b.properties['burst']['fullBurstID']}"
            burst_id = burst_id.lower() if lowercase else burst_id
            burst_st = datetime.strptime(
                b.properties["startTime"], "%Y-%m-%dT%H:%M:%SZ"
            )
            burst_geom = shapely.geometry.shape(b.geometry)
            pol = b.properties["polarization"].upper()
            if burst_id not in burst_info:
                burst_info[burst_id] = {
                    "start_time": burst_st,
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
    """Get the burst ids, start-times, polarisations and geometries for a scene from CDSE.
    Return as a dictionary of bursts as the keys, and start-times, polarisations and geometries as
    sub-dictionaries.

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
        unique dict of scene burst ids mapped to start_times, geometries and shapes
        {'t070_149822_IW3' : {start_time : datetime.datetime, geometry: shapely.geometry}}
    """

    base_url = "https://catalogue.dataspace.copernicus.eu/odata/v1/Bursts"
    query = f"$filter=ParentProductName eq '{scene}.SAFE'&$top=100"
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
        # get start-times and geometries
        burst_st = datetime.strptime(
            b.get("BeginningDateTime"), "%Y-%m-%dT%H:%M:%S.%fZ"
        )
        burst_geom = shapely.geometry.shape(b.get("GeoFootprint"))
        pol = b.get("PolarisationChannels").upper()

        if burst_id not in burst_info:
            burst_info[burst_id] = {
                "start_time": burst_st,
                "geometry": burst_geom,
                "pols": [pol],
            }
        elif burst_id in burst_info and pol not in burst_info[burst_id]["pols"]:
            burst_info[burst_id]["pols"].append(pol)

    if len(burst_info) == 0:
        raise FileExistsError(
            "No burst id's for scene could be found on the CDSE. Ensure input values are correct. "
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
    make_existing_products: bool,
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
    make_existing_products : bool
        whether to make products if they already exist in s3. If False,
        process will exit early if all already exist.
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
        # get the path to search for
        if product == "RTC_S1_STATIC":
            s3_product_subpath = make_rtc_s1_static_s3_subpath(
                s3_project_folder=s3_project_folder,
                collection_number=collection_number,
                burst_id=burst_id,
            )
        if product == "RTC_S1":
            s3_product_subpath = make_rtc_s1_s3_subpath(
                s3_project_folder=s3_project_folder,
                collection_number=collection_number,
                burst_polarisations=burst_polarisations,
                burst_id=burst_id,
                year=burst_st.year,
                month=burst_st.month,
                day=burst_st.day,
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
        f"No products already exist for the requested bursts."
        burst_id_list_to_process = burst_id_list

    # return the list of bursts that need to be processed
    return burst_id_list_to_process


def ensure_static_layers_in_s3(
    scene: str,
    burst_id_list,
    static_layers_s3_bucket: str,
    static_layers_collection_number: int,
    static_layers_s3_project_folder: str,
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
        static_layers_s3_folder = make_rtc_s1_static_s3_subpath(
            static_layers_s3_project_folder, static_layers_collection_number, burst_id
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
            f"E.g. re-run the workflow using `--product RTC_S1_STATIC --collection rtc_s1_static_c1.`\n"
            f"See workflow docs for details at docs/workflows/aws.md."
        )
        sys.exit(early_exit_code)
