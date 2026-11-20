import datetime
import re

GAMMA_RTC_S1_S3_PREFIX_FORMAT = "{s3_project_folder}/{odc_product_name}/{start_year}/{start_month}/{start_day}/{scene_id}"


def get_odc_product_name(
    product,
    collection_number,
    polarisations,
    acquisition_mode="iw",
    processing_software="",
):
    """get the odc product name. WARNING this must align with
    the DEA product name at indexing into the datacube.
    These are hard-coded and set by the provided `collection_number`.
    """
    product_prefix = "ga_s1_nrb"
    if processing_software:
        product_prefix += f"_{processing_software}"

    if product == "RTC_S1":
        if all([pol in polarisations for pol in ["VV", "VH"]]):
            return (
                f"{product_prefix}_{acquisition_mode.lower()}_vv_vh_{collection_number}"
            )
        elif all([pol in polarisations for pol in ["HH", "HV"]]):
            return (
                f"{product_prefix}_{acquisition_mode.lower()}_hh_hv_{collection_number}"
            )
        elif polarisations == ["VV"]:
            return f"{product_prefix}_{acquisition_mode.lower()}_vv_{collection_number}"
        elif polarisations == ["HH"]:
            return f"{product_prefix}_{acquisition_mode.lower()}_hh_{collection_number}"
        else:
            raise ValueError(
                "could not create odc product name from; "
                f"product: {product}, collection_number: {collection_number}, polarisations: {polarisations}, acquisition mode : {acquisition_mode}"
            )
    elif product == "RTC_S1_STATIC":
        return f"{product_prefix}_{acquisition_mode.lower()}_static_{collection_number}"
    else:
        raise ValueError(
            "could not create odc product name from; "
            f"product: {product}, collection_number: {collection_number}, polarisations: {polarisations}, acquisition mode : {acquisition_mode}"
        )


def make_gamma_rtc_s1_product_s3_prefix(
    s3_project_folder: str,
    collection_number: int,
    polarisations: list,
    acquisition_mode: str,
    scene_id: str,
    start_dt: str | datetime.datetime,
    processing_software: str,
) -> str:
    """Structure for the RTC_S1 pyrosar-GAMMA product sub-folders. These include
    information about when the product was acquired.

    Parameters
    ----------
    s3_project_folder : str
        s3 project folder
    collection_number : int
        collection number as an integer
    polarisations: list
        list of polarisations
    acquisition_mode: str
        Acquisition mode of sensor. E.g. IW, EW
    scene_id : str
        scene_id. e.g. S1A_EW_GRDM_1SDH_20190103T112546_20190103T112656_025312_02CCF2_83F6
    start_dt : str | datetime.datetime
        The starting datetime for the the product acquisition.
    processing_software : str
        The software used for processing the product. E.g. pyrosar-GAMMA

    Returns
    -------
    str
        path to the s3 bucket subfolder
        e.g. s3_project_folder/ga_s1_nrb_ew_vv_1/2022/01/01
    """

    # get the odc product name which includes the collection number
    # get the time values
    start_year = f"{start_dt.year}"
    # zero padded day and month strings
    start_month = f"{start_dt.month:02d}"
    start_day = f"{start_dt.day:02d}"

    # formatted timestamp without UTC 'Z'
    start_dt = start_dt.strftime("%Y%m%dT%H%M%S")

    # get the correct odc product name
    odc_product_name = get_odc_product_name(
        "RTC_S1",
        collection_number,
        polarisations,
        acquisition_mode=acquisition_mode,
        processing_software=processing_software,
    )

    # update the string format
    gamma_rtc_s1_s3_prefix = GAMMA_RTC_S1_S3_PREFIX_FORMAT.format(
        s3_project_folder=s3_project_folder,
        odc_product_name=odc_product_name,
        start_year=start_year,
        start_month=start_month,
        start_day=start_day,
        scene_id=scene_id,
    )

    return gamma_rtc_s1_s3_prefix
