import re


def get_collection_number(collection: str) -> int:
    """Get the collection number from the collection string

    Parameters
    ----------
    collection : str
        Collection of the product. e.g. s1_rtc_c1. The collection MUST end in cX where X
        is an integer associated with the collection. E.g. rtc_s1_c1.

    Returns
    -------
    int
        number. e.g. s1_rtc_c1 -> 1

    Raises
    ------
    ValueError
        Invalid collection name.
    """

    # ensure the collection ends with cX, where X is a positive integer
    match = re.search(r"c(\d+)$", collection)
    if not match:
        raise ValueError(
            f"Invalid collection name. The collection MUST end in cX where X"
            " is an integer associated with the collection. E.g. rtc_s1_c1."
        )
    return int(match.group(1))


def get_odc_product_name(product, collection_number, polarisations):
    """set the odc:product value. WARNING this must align with
    the DEA product name at indexing into the datacube.
    These are hard-coded and set by the provided `collection_number`.
    """
    if product == "RTC_S1":
        if all([pol in polarisations for pol in ["VV", "VH"]]):
            return f"ga_s1_iw_vv_vh_c{collection_number}"
        elif all([pol in polarisations for pol in ["HH", "HV"]]):
            return f"ga_s1_iw_hh_hv_c{collection_number}"
        elif polarisations == ["VV"]:
            return f"ga_s1_iw_vv_c{collection_number}"
        elif polarisations == ["HH"]:
            return f"ga_s1_iw_hh_c{collection_number}"
    elif product == "RTC_S1_STATIC":
        return f"ga_s1_iw_static_c{collection_number}"


def make_rtc_s1_s3_subpath(
    s3_project_folder: str,
    collection: str,
    burst_polarisations: list,
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
    burst_polarisations: list
        list of burst polarisations
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
        e.g. s3_project_folder/c1/s1_rtc_c1/ga_s1_iw_vv_c1/t028_059507_iw2/2022/01/01
    """
    # get collection name and number from input collection
    c_number = get_collection_number(collection)
    # get the odc product name which includes the collection
    odc_product_name = get_odc_product_name("RTC_S1", c_number, burst_polarisations)
    return f"{s3_project_folder}/c{c_number}/{collection}/{odc_product_name}/{burst_id}/{year}/{month}/{day}"


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
        e.g. s3_project_folder/c1/s1_rtc_static_c1/ga_s1_iw_static_c1/t028_059507_iw2
    """
    # get collection name and number from input collection
    c_number = get_collection_number(collection)
    # get the odc product name which includes the collection
    odc_product_name = get_odc_product_name("RTC_S1_STATIC", c_number, [])
    return f"{s3_project_folder}/c{c_number}/{collection}/{odc_product_name}/{burst_id}"


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
