import datetime


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


def make_rtc_s1_s3_subpath(
    s3_project_folder: str,
    collection_number: int,
    burst_polarisations: list,
    burst_id: str,
    burst_st: datetime.datetime,
):
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
    burst_st : datetime.datetime
        The starting datetime for the the burst acquisition

    Returns
    -------
    str
        path to the s3 bucket subfolder
        e.g. s3_project_folder/ga_s1_nrb_iw_vv_c1/t028_059507_iw2/2022/01/01
    """

    # get the odc product name which includes the collection number
    burst_st_fmt = burst_st.strftime(
        "%Y%m%dT%H%M%S"
    )  # formatted timestamp without UTC 'Z'
    odc_product_name = get_odc_product_name(
        "RTC_S1", collection_number, burst_polarisations
    )
    return f"{s3_project_folder}/{odc_product_name}/{burst_id}/{burst_st.year}/{burst_st.month:02d}/{burst_st.day:02d}/{burst_st_fmt}"


def make_rtc_s1_static_s3_subpath(
    s3_project_folder: str,
    collection_number: int,
    burst_id: str,
) -> str:
    """Structure for the bucket subpath for static layers

    Parameters
    ----------
    s3_project_folder : str
        s3 project folder
    collection_number : int
        collection number as an integer
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
    return f"{s3_project_folder}/{odc_product_name}/{burst_id}"


def make_static_layer_browse_url(
    static_layers_s3_bucket: str,
    static_layers_collection_number: int,
    static_layers_s3_project_folder: str,
    burst_id: str = "",
    s3_region: str = "ap-southeast-2",
) -> str:
    """Make the browse url to the static layers from the paths provided

    Parameters
    ----------
    static_layers_s3_bucket : str
        Bucket containing static layer
    static_layers_collection_number : int
        collection number of the static layers
    static_layers_s3_project_folder : str
        project folder within bucket if exists
    burst_id:
        burst id. If not supplied, the root browse link to all static
        layers is created.

    s3_region : str, optional
        aws region code, by default "ap-southeast-2"

    Returns
    -------
    str
        The url to the index file where static layers are stored for user
        visibility
    """
    static_layer_path = make_rtc_s1_static_s3_subpath(
        s3_project_folder=static_layers_s3_project_folder,
        collection_number=static_layers_collection_number,
        burst_id=burst_id,
    )
    return (
        f"https://{static_layers_s3_bucket}.s3.{s3_region}.amazonaws.com"
        f"/index.html?prefix={static_layer_path}"
    )
