import asf_search
from datetime import datetime, timedelta
import boto3
import os
import logging
import s1reader
from typing import Literal
import sys

from sar_pipeline.aws.metadata.filetypes import REQUIRED_ASSET_FILETYPES
from sar_pipeline.nci.preparation.scenes import parse_scene_file_dates

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_aws_environment_credentials():
    # search for credentials in environment and raise warning if not there
    if os.environ.get("AWS_ACCESS_KEY_ID") is None:
        wrn_msg = "AWS_ACCESS_KEY_ID is not set in environment variables. Set if authentication required on bucket"
        logging.warning(wrn_msg)
    if os.environ.get("AWS_SECRET_ACCESS_KEY") is None:
        wrn_msg = "AWS_ACCESS_KEY_ID is not set in environment variables. Set if authentication required on bucket"
        logging.warning(wrn_msg)
    if os.environ.get("AWS_DEFAULT_REGION") is None:
        wrn_msg = "AWS_DEFAULT_REGION is not set in environment variables. Set if authentication required on bucket"
        logging.warning(wrn_msg)


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

    check_aws_environment_credentials()
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


def get_burst_ids_and_start_times_for_scene_from_asf(
    scene: str, burst_prefix: str = "t", lowercase: bool = True
) -> tuple[list[str], list[datetime]]:
    """Get the list of burst_ids corresponding to a scene

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
    tuple[list[str],list[datetime]]
        List of burst ids. e.g. ['t070_149822_IW3','t070_149822_IW2' ....]
        List of sensing start times corresponding to each above burst ids.
    """

    st, et = parse_scene_file_dates(scene)

    results = asf_search.search(
        platform=[asf_search.PLATFORM.SENTINEL1],
        maxResults=100,
        processingLevel="BURST",
        start=st - timedelta(seconds=1),
        end=et + timedelta(seconds=1),
    )

    burst_ids = [
        f"{burst_prefix}{b.properties['burst']['fullBurstID']}"
        for b in results
        if scene in b.properties["url"]
    ]
    burst_sts = [
        datetime.strptime(b.properties["startTime"], "%Y-%m-%dT%H:%M:%SZ")
        for b in results
        if scene in b.properties["url"]
    ]
    if lowercase:
        burst_ids = [b.lower() for b in burst_ids]

    if len(burst_ids) == 0:
        raise FileExistsError(
            "No burst id's for scene could be found on the ASF. Ensure input values are correct "
            "or set `--scene_data_source CDSE` as recent scenes may not be available on ASF, or the scene is missing"
        )

    return burst_ids, burst_sts


def make_static_layer_base_url(
    static_layers_s3_bucket: str,
    static_layers_collection: str,
    static_layers_s3_project_folder: str,
    s3_region: str = "ap-southeast-2",
) -> str:
    """Make the base url to the static layers from the paths provided

    Parameters
    ----------
    static_layers_s3_bucket : str
        Bucket containing static layer
    static_layers_collection : str
        collection static layers belong to
    static_layers_s3_project_folder : str
        project folder within bucket if exists
    s3_region : str, optional
        aws region code, by default "ap-southeast-2"

    Returns
    -------
    str
        The url to the index file where static layers are stored for user
        visibility
    """
    root_static_layer_path = make_rtc_s1_static_s3_subpath(
        s3_project_folder=static_layers_s3_project_folder,
        collection=static_layers_collection,
        burst_id="",
    )
    return (
        f"https://{static_layers_s3_bucket}.s3.{s3_region}.amazonaws.com"
        f"/index.html?prefix={root_static_layer_path}"
    )


def check_burst_products_exists_in_s3(
    product: Literal["RTC_S1", "RTC_S1_STATIC"],
    burst_id_list: list[str],
    burst_st_list: list[str],
    s3_bucket: str,
    s3_project_folder: str,
    collection: str,
    make_existing_products: bool,
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
    collection : str
        The collection. e.f. rtc_s1_c1
    make_existing_products : bool
        whether to make products if they already exist in s3. If False,
        process will exit early if all already exist.

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
        if product == "RTC_S1_STATIC":
            s3_product_subpath = make_rtc_s1_static_s3_subpath(
                s3_project_folder=s3_project_folder,
                collection=collection,
                burst_id=burst_id,
            )
        if product == "RTC_S1":
            s3_product_subpath = make_rtc_s1_s3_subpath(
                s3_project_folder=s3_project_folder,
                collection=collection,
                burst_id=burst_id,
                year=burst_st.year,
                month=burst_st.month,
                day=burst_st.day,
            )
        # assume the product exists if there is a .h5 file
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
            burst_id_list = [b for b in burst_id_list if b not in existing_burst_ids]
            logger.warning(
                "Skipping the existing products. To create these, remove the existing products from S3. OR, pass flag "
                "'--make-existing-products' to workflow. WARNING this can create duplicates that may impact downstream processes."
            )
            # exit if all existing burst products exist
            if all(b in existing_burst_ids for b in burst_id_list):
                logging.warning(
                    "All desired burst products already exist, exiting process early"
                )
                sys.exit(100)
        else:
            logger.warning(
                "Existing products are being re-created. WARNING This will create duplicates in the S3 bucket that may impact downstream processes. "
                "set '--make-existing-products' if this behavior is not desired."
            )

    return burst_id_list


def make_rtc_s1_s3_subpath(
    s3_project_folder: str,
    collection: str,
    burst_id: str,
    year: str,
    month: str,
    day: str,
):
    """Structure for the rtc_s1 product sub-folders. These include
    information about when the burst was acquired.

    Parameters
    ----------
    s3_project_folder : str
        s3 project folder
    collection : str
        collection. e.g. rtc_s1_static_c1
    burst_id : str
        burst_id. e.g. t028_059507_iw2
    year : str
        year of burst acquisition
    month : str
        month of burst acquisition
    day : str
        day of burst acquisition

    Returns
    -------
    str
        path to the s3 bucket subfolder
        e.g. my-subfolder/s1_rtc_c1/t028_059507_iw2/2022/01/01
    """
    return f"{s3_project_folder}/{collection}/{burst_id}/{year}/{month}/{day}"


def make_rtc_s1_static_s3_subpath(
    s3_project_folder: str,
    collection: str,
    burst_id: str,
) -> str:
    """Structure for the bucket subpath for static layers

    Parameters
    ----------
    s3_project_folder : str
        s3 project folder
    collection : str
        collection. e.g. rtc_s1_static_c1
    burst_id : str
        burst_id. e.g. t028_059507_iw2

    Returns
    -------
    str
        path to the s3 bucket subfolder
        e.g. my-subfolder/s1_rtc_static_c1/t028_059507_iw2
    """

    return f"{s3_project_folder}/{collection}/{burst_id}"


def check_static_layers_in_s3(
    scene: str,
    burst_id_list,
    static_layers_s3_bucket: str,
    static_layers_collection: str,
    static_layers_s3_project_folder: str,
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
    static_layers_collection : str
        collection folder for the static layers
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
        static_layers_s3_folder = (
            f"{static_layers_s3_project_folder}/{static_layers_collection}/{burst_id}"
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
        raise FileExistsError(
            f"\nMissing static layers for bursts in scene : {scene}\n"
            f"{n_missing} of {n_bursts} required bursts have files missing.\n"
            f"Missing Bursts and static layer filetypes:\n"
            f"{missing_info}\n"
            f"Example AWS S3 path searched : {static_layers_s3_bucket}/{static_layers_s3_folder}\n"
            f"Check linked location arguments or create the missing static layers. "
            f"E.g. re-run the workflow using `--product RTC_S1_STATIC --collection rtc_s1_static_c1.`\n"
            f"See workflow docs for details at docs/workflows/aws.md."
        )
