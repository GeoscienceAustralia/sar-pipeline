import boto3
import re
from datetime import datetime
from pathlib import Path
from typing import List
from typing import Literal
import tempfile
import logging
import json

from sar_pipeline.utils.aws import S3Util
from sar_pipeline.pipelines.isce3_rtc.monitoring.generate_s1_iw_completeness_report import (
    COMPLETENESS_REPORT_FORMAT,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ValidReportTypes = Literal["scene", "burst"]


def _send_job_to_sqs(queue_url: str, job: dict) -> None:

    sqs = boto3.client("sqs")
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(job),
    )


def _parse_s3_folder_for_most_recent_completeness_reports(
    report_type: ValidReportTypes,
    s3_bucket: str,
    s3_folder: str,
    n_most: int = 1,
) -> List[str]:
    """
    Find the N most recent completeness reports in an S3 folder for a given report type.

    Parameters
    ----------
    report_type : Literal["scene", "burst"]
        Type of report
    s3_bucket : str
        Name of the S3 bucket
    s3_folder : str
        Path to the folder inside the bucket (no trailing slash)
    n_most : int, optional
        Number of most recent reports to return, by default 1

    Returns
    -------
    list[str]
        List of S3 keys for the most recent reports (newest first)

    Raises
    ------
    ValueError
        If no matching reports are found
    """
    s3 = boto3.client("s3")

    paginator = s3.get_paginator("list_objects_v2")
    page_iterator = paginator.paginate(
        Bucket=s3_bucket,
        Prefix=f"{s3_folder}/",
    )

    report_names = []

    for page in page_iterator:
        for obj in page.get("Contents", []):
            key = obj["Key"]

            if f"{report_type}_completeness_report" not in key:
                continue

            report_name = Path(key).name

            try:
                report_time = datetime.strptime(
                    report_name.split("_")[0], "%Y%m%dT%H%M%S"
                )
            except ValueError:
                # Skip malformed filenames rather than failing hard
                continue

            report_names.append((report_time, key))

    if not report_names:
        raise ValueError(
            f"Could not find completeness reports for "
            f"s3_bucket={s3_bucket}, s3_folder={s3_folder}, report_type={report_type}"
        )

    # Sort newest first
    report_names.sort(key=lambda x: x[0], reverse=True)

    return [key for _, key in report_names[:n_most]]


def process_s1_iw_scene_completeness_report(
    s3_bucket: str,
    s3_completeness_report_folder: str,
    report_name: str,
    n_most_recent_reports: int = None,
    s1_rtc_sqs_url: str = "https://sqs.ap-southeast-2.amazonaws.com/451924316694/s1-rtc-simulate-batch-queue",
    dry_run: bool = False,
):

    if not (report_name or n_most_recent_reports) or (
        report_name and n_most_recent_reports
    ):
        raise ValueError(
            "`report_name` (e.g. 20260113T000323__20241201T000000__20241201T002000_scene_completeness_report.json) OR "
            "`n_most_recent_reports` parameter must be set to either process a specific report, or the most recent n reports. "
            "e.g. set `n_most_recent_reports = 1` to process the most recently created scene report. "
        )

    if n_most_recent_reports:
        # find the n most recent report
        completeness_report_s3_keys = (
            _parse_s3_folder_for_most_recent_completeness_reports(
                report_type=report_type,
                s3_folder=s3_completeness_report_folder,
                s3_bucket=s3_bucket,
                n_most=n_most_recent_reports,
            )
        )
        logging.info(
            f"Using latest {n_most_recent_reports} completion report/s : {completeness_report_s3_keys}"
        )
        completeness_report_s3_key = completeness_report_s3_keys[0]
    else:
        # use the report specified
        completeness_report_s3_keys = [
            Path(s3_completeness_report_folder) / report_name
        ]
        logging.info(
            f"Attempting to use specified completion report : {completeness_report_s3_keys[0]}"
        )

    s3_downloader = S3Util()

    for i, completeness_report_s3_key in enumerate(completeness_report_s3_keys):
        logging.info(f"Processing report {i+1} of {len(completeness_report_s3_keys)}")
        logger.info(f"Report name : {Path(completeness_report_s3_key).name}")
        with tempfile.NamedTemporaryFile("w+b") as tmpfile:
            # download writes bytes directly
            s3_downloader.s3.download_fileobj(
                s3_bucket, completeness_report_s3_key, tmpfile
            )
            # rewind to start of file
            tmpfile.seek(0)
            # load JSON
            report_data = json.load(tmpfile)

        # logger.info(f"report_time : {completeness_report['report_time']}")
        # logger.info(f"search_start_time : {completeness_report['search_start_time']}")
        # logger.info(f"search_end_time : {completeness_report['search_end_time']}")
        # logger.info(f"search_geometry : {completeness_report['search_geometry']}")
        # logger.info(f"summary : {json.dumps(completeness_report['summary'], indent=2)}")


def process_s1_iw_burst_completeness_report(
    s3_bucket: str,
    s3_completeness_report_folder: str,
    report_name: str = None,
    n_most_recent_reports: int = None,
    s1_rtc_sqs_url: str = "https://sqs.ap-southeast-2.amazonaws.com/451924316694/s1-rtc-simulate-batch-queue",
    s1_rtc_static_sqs_url: str = "https://sqs.ap-southeast-2.amazonaws.com/451924316694/s1-rtc-static-queue",
    dry_run: bool = False,
): ...


if __name__ == "__main__":

    s3_bucket = "deant-data-public-dev"
    s3_completeness_report_folder = "TMP/completeness_reports"
    report_type = "burst"
    report_name = ""
    n_most_recent_reports = 2

    process_s1_iw_scene_completeness_report(
        s3_bucket,
        s3_completeness_report_folder,
        report_name=None,
        n_most_recent_reports=1,
        s1_rtc_sqs_url="https://sqs.ap-southeast-2.amazonaws.com/451924316694/s1-rtc-simulate-batch-queue",
        dry_run=False,
    )
