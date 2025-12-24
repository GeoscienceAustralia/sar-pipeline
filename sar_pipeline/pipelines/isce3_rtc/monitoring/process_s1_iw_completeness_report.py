import boto3
import re
from datetime import datetime
from pathlib import Path
from typing import Optional
from typing import Literal
import tempfile
import logging
import json
from pprint import pprint

from sar_pipeline.utils.aws import S3Util
from sar_pipeline.pipelines.isce3_rtc.monitoring.generate_s1_iw_completeness_report import (
    COMPLETENESS_REPORT_FORMAT,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ValidReportTypes = Literal["scene", "burst"]


def _parse_s3_folder_for_most_recent_completeness_report(
    report_type: ValidReportTypes,
    s3_bucket: str,
    s3_folder: str,
) -> str:
    """
    Find the most recent completeness report in an S3 folder for a given report type.

    Parameters
    ----------
    report_type : Literal["scene","burst"]
        Type of report, e.g., " burst" or "scene"
    s3_bucket : str
        Name of the S3 bucket
    s3_folder : str
        Path to the folder inside the bucket (no trailing slash)

    Returns
    -------
    str
        S3 key of the most recent report, or None if no reports found.
    """
    s3 = boto3.client("s3")

    paginator = s3.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(Bucket=s3_bucket, Prefix=s3_folder + "/")

    latest_report = None
    latest_report_time = None

    for page in page_iterator:
        for obj in page.get("Contents", []):
            key = obj["Key"]
            if f"{report_type}_completeness_report" in key:
                report_name = Path(key).name
                # report time is the most recent report
                report_time = datetime.strptime(
                    report_name.split("_")[0], "%Y%m%dT%H%M%S"
                )
                if latest_report_time is None or report_time > latest_report_time:
                    latest_report_time = report_time
                    latest_report = key

    if not latest_report:
        raise ValueError(
            f"Could not find completeness report for "
            f"s3_bucket : {s3_bucket}, s3_folder : {s3_folder}, report_type : {report_type}"
        )

    return latest_report


def submit_missing_scenes_to_reprocess_from_scene_completeness_report(): ...


def submit_missing_scenes_to_reprocess_from_burst_completeness_report(): ...


def submit_static_layers_to_reprocess_from_burst_completeness_report(): ...


def submit_bursts_to_index_from_burst_completeness_report(): ...


if __name__ == "__main__":

    s3_bucket = "deant-data-public-dev"
    s3_completeness_report_folder = "TMP/completeness_reports"
    report_type = "burst"
    report_name = "latest"

    if report_name == "latest":
        # fine the latest report

        completeness_report_s3_key = (
            _parse_s3_folder_for_most_recent_completeness_report(
                report_type=report_type,
                s3_folder=s3_completeness_report_folder,
                s3_bucket=s3_bucket,
            )
        )
        logging.info(f"Using latest completion report : {completeness_report_s3_key}")
    else:
        # use the report specified
        completeness_report_s3_key = Path(s3_completeness_report_folder) / report_name
        logging.info(
            f"Attempting to use completed report : {completeness_report_s3_key}"
        )

    s3_downloader = S3Util()
    with tempfile.NamedTemporaryFile("w+b") as tmpfile:
        # download writes bytes directly
        s3_downloader.s3.download_fileobj(
            s3_bucket, completeness_report_s3_key, tmpfile
        )
        # rewind to start of file
        tmpfile.seek(0)
        # load JSON
        completeness_report = json.load(tmpfile)

    logger.info(f"Report name : {Path(completeness_report_s3_key).name}")
    logger.info(f"report_time : {completeness_report['report_time']}")
    logger.info(f"search_start_time : {completeness_report['search_start_time']}")
    logger.info(f"search_end_time : {completeness_report['search_end_time']}")
    logger.info(f"search_geometry : {completeness_report['search_geometry']}")
    logger.info(f"summary : {json.dumps(completeness_report['summary'], indent=2)}")
