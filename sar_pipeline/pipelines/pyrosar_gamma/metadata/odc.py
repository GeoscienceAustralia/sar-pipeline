import datetime
import re

from sar_pipeline.pipelines.isce3_rtc.metadata.odc import get_odc_product_name

GAMMA_RTC_S1_S3_PREFIX_FORMAT = "{s3_project_folder}/{odc_product_name}/{start_year}/{start_month}/{start_day}/{scene_id}"


def make_gamma_rtc_s1_product_s3_prefix(
    s3_project_folder: str,
    collection_number: int,
    polarisations: list,
    mode: str,
    scene_id: str,
    start_dt: str | datetime.datetime,
) -> str:
    """Structure for the RTC_S1 product sub-folders. These include
    information about when the burst was acquired.

    Parameters
    ----------
    s3_project_folder : str
        s3 project folder
    collection_number : int
        collection number as an integer
    polarisations: list
        list of polarisations
    mode: str
        Acquisition mode of sensor. E.g. IW, EW
    scene_id : str
        burst_id. e.g. S1A_EW_GRDM_1SDH_20190103T112546_20190103T112656_025312_02CCF2_83F6
    start_dt : str | datetime.datetime
        The starting datetime for the the burst acquisition.

    Returns
    -------
    str
        path to the s3 bucket subfolder
        e.g. s3_project_folder/ga_s1_nrb_ew_vv_1/2022/01/01
    """

    # get the odc product name which includes the collection number
    # get the time values
    start_year = f"{start_dt.year}"
    start_month = f"{start_dt.month:02d}"
    start_day = f"{start_dt.day:02d}"

    start_dt = start_dt.strftime("%Y%m%dT%H%M%S")  # formatted timestamp without UTC 'Z'
    # zero padded day and month strings

    # get the correct odc product name
    odc_product_name = get_odc_product_name(
        "RTC_S1", collection_number, polarisations, acquisition_mode=mode
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
