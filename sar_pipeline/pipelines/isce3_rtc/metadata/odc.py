import datetime
import re
from sar_pipeline.utils.dem import ValidDemType

# Define the format of the s3 prefix, i.e. final s3 folder for each product
# Note the st refers to the burst azimuth time, as this is the start time / sensing_start
# considered by s1_reader -> https://github.com/isce-framework/s1-reader/blob/v0.2.5/src/s1reader/s1_reader.py#L1044
RTC_S1_S3_PREFIX_FORMAT = "{s3_project_folder}/{odc_product_name}/{burst_id}/{burst_st_year}/{burst_st_month}/{burst_st_day}/{burst_st}"
RTC_S1_STATIC_S3_PREFIX_FORMAT = "{s3_project_folder}/{odc_product_name}/{burst_id}/{static_layer_validity_start_date}/{dem_type}"


def get_odc_product_name(product, collection_number, polarisations):
    """get the odc product name. WARNING this must align with
    the DEA product name at indexing into the datacube.
    These are hard-coded and set by the provided `collection_number`.
    """
    if product == "RTC_S1":
        if all([pol in polarisations for pol in ["VV", "VH"]]):
            return f"ga_s1_nrb_iw_vv_vh_{collection_number}"
        elif all([pol in polarisations for pol in ["HH", "HV"]]):
            return f"ga_s1_nrb_iw_hh_hv_{collection_number}"
        elif polarisations == ["VV"]:
            return f"ga_s1_nrb_iw_vv_{collection_number}"
        elif polarisations == ["HH"]:
            return f"ga_s1_nrb_iw_hh_{collection_number}"
        else:
            raise ValueError(
                "could not create odc product name from; "
                f"product: {product}, collection_number: {collection_number}, polarisations: {polarisations}"
            )
    elif product == "RTC_S1_STATIC":
        return f"ga_s1_nrb_iw_static_{collection_number}"
    else:
        raise ValueError(
            "could not create odc product name from; "
            f"product: {product}, collection_number: {collection_number}, polarisations: {polarisations}"
        )


def make_rtc_s1_product_s3_prefix(
    s3_project_folder: str,
    collection_number: int,
    burst_polarisations: list,
    burst_id: str,
    burst_st: str | datetime.datetime,
    burst_st_year: int | str | None = None,
    burst_st_month: int | str | None = None,
    burst_st_day: int | str | None = None,
) -> str:
    """Structure for the RTC_S1 product sub-folders. These include
    information about when the burst was acquired.

    Parameters
    ----------
    s3_project_folder : str
        s3 project folder
    collection_number : int
        collection number as an integer
    burst_polarisations: list
        list of burst polarisations
    burst_id : str
        burst_id. e.g. t028_059507_iw2
    burst_st : str | datetime.datetime
        The starting datetime for the the burst acquisition.
        should be of format "%Y%m%dT%H%M%S". This is considered to
        be azimuth_time in the RTC workflow.
    burst_st_year : int | str | None
        The starting year for the the burst acquisition.
        If None, will be retrieved from burst_st. Considered to be
        azimuth_time in the RTC workflow.
    burst_st_month : int | str | None
        The starting month for the the burst acquisition. Single digit months
        should be zero padded. If None, will be retrieved from burst_st.
        Considered to be azimuth_time in the RTC workflow.
    burst_st_day : int | str | None
        The starting day for the the burst acquisition. Single digit days
        should be zero padded. If None, will be retrieved from burst_st.
        Considered to be azimuth_time in the RTC workflow.

    Returns
    -------
    str
        path to the s3 bucket subfolder
        e.g. s3_project_folder/ga_s1_nrb_iw_vv_c1/t028_059507_iw2/2022/01/01
    """

    # get the odc product name which includes the collection number
    if isinstance(burst_st, datetime.datetime):

        # get the time values if not provided
        burst_st_year = f"{burst_st.year}" or burst_st_year
        burst_st_month = f"{burst_st.month:02d}" or burst_st_month
        burst_st_day = f"{burst_st.day:02d}" or burst_st_day

        burst_st = burst_st.strftime(
            "%Y%m%dT%H%M%S"
        )  # formatted timestamp without UTC 'Z'
        # zero padded day and month strings

    if isinstance(burst_st, str) and not all(
        [burst_st_year, burst_st_day, burst_st_month]
    ):
        raise ValueError(
            "burst_st must be provided as a datetime.datetime if burst_st_year, "
            "burst_st_day, burst_st_month are not all provided."
        )

    # get the correct odc product name
    odc_product_name = get_odc_product_name(
        "RTC_S1", collection_number, burst_polarisations
    )

    # update the string format
    rtc_s1_s3_prefix = RTC_S1_S3_PREFIX_FORMAT.format(
        s3_project_folder=s3_project_folder,
        odc_product_name=odc_product_name,
        burst_id=burst_id,
        burst_st_year=burst_st_year,
        burst_st_month=burst_st_month,
        burst_st_day=burst_st_day,
        burst_st=burst_st,
    )

    return rtc_s1_s3_prefix


def make_rtc_s1_static_product_s3_prefix(
    s3_project_folder: str,
    collection_number: int,
    dem_type: ValidDemType,
    static_layer_validity_start_date: int,
    burst_id: str,
) -> str:
    """Structure for the bucket subpath for static layers

    Parameters
    ----------
    s3_project_folder : str
        s3 project folder
    collection_number : int
        collection number as an integer
    dem_type : str, ValidDemType
        The dem type used for processing.
    static_layer_validity_start_date : int
        The validity start date for the static layers used in processing,
        expressed in YYYYMMDD format.
    burst_id : str
        burst_id. e.g. t028_059507_iw2

    Returns
    -------
    str
        path to the s3 bucket subfolder
        e.g. s3_project_folder/ga_s1_nrb_iw_static_c1/t028_059507_iw2
    """
    # get the odc product name which includes the collection number
    odc_product_name = get_odc_product_name("RTC_S1_STATIC", collection_number, [])

    # update the string format
    rtc_s1_static_s3_prefix = RTC_S1_STATIC_S3_PREFIX_FORMAT.format(
        s3_project_folder=s3_project_folder,
        odc_product_name=odc_product_name,
        dem_type=dem_type,
        static_layer_validity_start_date=static_layer_validity_start_date,
        burst_id=burst_id,
    )

    return rtc_s1_static_s3_prefix


def make_rtc_s1_static_product_browse_url(
    s3_bucket: str,
    rtc_s1_static_s3_prefix: str,
    s3_region: str = "ap-southeast-2",
) -> str:
    """Make the browse url to the static layer product from the paths provided

    Parameters
    ----------
    static_layers_s3_bucket : str
        Bucket containing static layer
    rtc_s1_static_s3_prefix : str
        product folder s3 path
    s3_region : str, optional
        aws region code, by default "ap-southeast-2"

    Returns
    -------
    str
        The url to the index file where static layers are stored for user
        visibility
    """

    return (
        f"https://{s3_bucket}.s3.{s3_region}.amazonaws.com"
        f"/index.html?prefix={rtc_s1_static_s3_prefix}"
    )


def make_rtc_s1_product_browse_url(
    s3_bucket: str,
    rtc_s1_s3_prefix: str,
    s3_region: str = "ap-southeast-2",
):
    """Make the browse url for the burst product.

    Parameters
    ----------
    s3_bucket : str
        Bucket containing product
    rtc_s1_s3_prefix: str,
        s3 subfolder for product
    s3_region : str, optional
        aws region code, by default "ap-southeast-2"

    Returns
    -------
    str
        URL to the index file where burst products are stored for user
        visibility
    """

    return (
        f"https://{s3_bucket}.s3.{s3_region}.amazonaws.com"
        f"/index.html?prefix={rtc_s1_s3_prefix}"
    )


def get_s3_prefix_from_product_browse_url(browse_url: str) -> str:
    """Get the s3_subpath from the browse link. Removes the path following "?prefix="

    Parameters
    ----------
    browse_url : str
        A URL to browse either the rtc_s1 or rtc_s1_static product subfolder created
        with either make_static_layer_browse_url or make_rtc_s1_burst_browse_url.


    Returns
    -------
    str
        s3 folder subpath. e.g. baseline/cop_glo30/20140403/ga_s1_nrb_iw_static_1/t045_095837_iw1/

    Examples
    -------
    https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=baseline/ga_s1_nrb_iw_hh_1/t070_149815_iw3/2022/01/01/20220101T124752/
    -> baseline/ga_s1_nrb_iw_hh_1/t070_149815_iw3/2022/01/01/20220101T124752/

    https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=baseline/cop_glo30/20140403/ga_s1_nrb_iw_static_1/t045_095837_iw1/
    -> baseline/cop_glo30/20140403/ga_s1_nrb_iw_static_1/t045_095837_iw1/
    """

    try:
        burst_s3_prefix = browse_url.split("?prefix=")[1]
    except:
        raise ValueError(
            f"Could not extract valid s3 subpath from the browse link provided: {browse_url}"
        )

    return burst_s3_prefix


def get_s3_bucket_from_product_browse_url(browse_url: str) -> str:
    """Get the s3_bucket from the browse link - removes the s3_bucket from the url string.

    Parameters
    ----------
    burst_url : str
        A URL to browse either the rtc_s1 or rtc_s1_static product subfolder created
        with either make_static_layer_browse_url or make_rtc_s1_burst_browse_url.

    Returns
    -------
    str
        s3 bucket. e.g. deant-data-public-dev

    Examples
    -------
    https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=baseline/ga_s1_nrb_iw_hh_1/t070_149815_iw3/2022/01/01/20220101T124752/
    -> deant-data-public-dev

    """
    bucket_match = re.search(r"https:\/\/([^\.]+)\.s3", browse_url)
    if bucket_match:
        s3_bucket = bucket_match.group(1)
    else:
        raise ValueError(
            f"Could not extract s3_bucket from the browse link provided: {browse_url}"
        )

    return s3_bucket
