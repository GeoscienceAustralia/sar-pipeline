import boto3
from datetime import datetime
from pathlib import Path
from typing import List
from typing import Literal
import tempfile
import logging
import json

from sar_pipeline.utils.aws import S3Util

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

ValidReportTypes = Literal["scene", "burst"]
VALID_REPORT_TYPES = ["scene", "burst"]


def _send_job_to_sqs(queue_url: str, job: dict) -> None:

    sqs = boto3.client("sqs")
    sqs.send_message(
        QueueUrl=queue_url,
        MessageBody=json.dumps(job),
    )


def _get_estimated_count_of_sqs_messages(queue_url: str):

    sqs = boto3.client("sqs")
    attrs = sqs.get_queue_attributes(
        QueueUrl=queue_url,
        AttributeNames=[
            "ApproximateNumberOfMessages",
            "ApproximateNumberOfMessagesNotVisible",
            "ApproximateNumberOfMessagesDelayed",
        ],
    )
    approx_visible = int(attrs["Attributes"]["ApproximateNumberOfMessages"])
    approx_inflight = int(attrs["Attributes"]["ApproximateNumberOfMessagesNotVisible"])
    approx_delayed = int(attrs["Attributes"]["ApproximateNumberOfMessagesDelayed"])

    return approx_visible + approx_inflight + approx_delayed


def _read_sqs_messages(queue_url, max_messages=10, wait_time=0):

    sqs = boto3.client("sqs")

    response = sqs.receive_message(
        QueueUrl=queue_url,
        MaxNumberOfMessages=max_messages,
        WaitTimeSeconds=wait_time,  # long polling
        VisibilityTimeout=60,  # seconds
    )
    return response.get("Messages", [])


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

    if report_type not in VALID_REPORT_TYPES:
        raise ValueError(f"Invalid `report_type`. Must be one of {VALID_REPORT_TYPES}")

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


def process_completeness_report(
    s3_bucket: str,
    s3_completeness_report_folder: str,
    report_type: ValidReportTypes,
    s1_nrb_sqs_url: str,
    report_name: str | None = None,
    n_most_recent_reports: int = None,
    remove_resubmitted_scenes_from_dlq=True,
    s1_nrb_dlq_sqs_url: str | None = None,
    s1_nrb_static_sqs_url: str = None,
    s1_nrb_indexing_sqs_url: str = None,
    dry_run: bool = False,
):

    logger.info("Called process_s1_iw_completeness_report with arguments:")
    for k, v in locals().items():
        logger.info(f"   {k} : {v}")

    if report_type not in VALID_REPORT_TYPES:
        raise ValueError(f"Invalid `report_type`. Must be one of {VALID_REPORT_TYPES}")

    if remove_resubmitted_scenes_from_dlq:
        if not s1_nrb_dlq_sqs_url:
            raise ValueError(
                f"A dead-letter queue must be set with `s1_nrb_dlq_sqs_url` if "
                "`remove_resubmitted_scenes_from_dlq` = True"
            )

    if not (report_name or n_most_recent_reports) or (
        report_name and n_most_recent_reports
    ):
        raise ValueError(
            "`report_name` (e.g. 20260113T000323__20241201T000000__20241201T002000_scene_completeness_report.json) OR "
            "`n_most_recent_reports` parameter must be set to either process a specific report, or the most recent n reports. "
            "e.g. set `n_most_recent_reports = 1` to process the most recently created scene report. "
        )
    if report_type == "burst":
        if not (s1_nrb_static_sqs_url or s1_nrb_indexing_sqs_url):
            raise ValueError(
                "Both `s1_nrb_static_sqs_url` and `s1_nrb_indexing_sqs_url` must be set if `report_type` == 'burst'. "
                "Missing static layers will be sent to reprocess and existing products not indexed will be added. "
                f"s1_nrb_static_sqs_url = {s1_nrb_static_sqs_url}, s1_nrb_indexing_sqs_url = {s1_nrb_indexing_sqs_url}"
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
            str(Path(s3_completeness_report_folder) / report_name)
        ]
        logging.info(
            f"Attempting to use specified completion report : {completeness_report_s3_keys[0]}"
        )

    s3_downloader = S3Util()

    # create a dict indexed by the s3_project_folder in case there are multiple
    # target folders in the completion reports
    s3_project_folders = []
    scenes_to_reprocess = {}
    scenes_w_missing_static_layers = {}
    burst_products_to_index = {}

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

            # print key info from report
            logger.info(f"report_time : {report_data['report_time']}")
            logger.info(f"search_start_time : {report_data['search_start_time']}")
            logger.info(f"search_end_time : {report_data['search_end_time']}")
            logger.info(f"s3_project_folder : {report_data['s3_project_folder']}")
            logger.info(f"summary : {json.dumps(report_data['summary'], indent=2)}")

            s3_project_folder = report_data["s3_project_folder"]
            if s3_project_folder not in s3_project_folders:
                s3_project_folders.append(s3_project_folder)

            # get the scenes to reprocess
            for scene in report_data["results"]["scenes_to_reprocess"]:
                if s3_project_folder not in scenes_to_reprocess.keys():
                    scenes_to_reprocess[s3_project_folder] = []
                if scene not in scenes_to_reprocess[s3_project_folder]:
                    scenes_to_reprocess[s3_project_folder].append(scene)

            # Get the scenes with missing static layers and burst products that
            # Exist but need to be indexed - ONLY AVAILABLE IN BURST REPORTS
            if report_type == "burst":
                # get the scenes with missing static layers to be sent to the
                # static layer sqs queue
                for scene in report_data["results"][
                    "scenes_with_missing_static_layers_to_reprocess"
                ]:
                    if s3_project_folder not in scenes_w_missing_static_layers.keys():
                        scenes_w_missing_static_layers[s3_project_folder] = []
                    if scene not in scenes_w_missing_static_layers[s3_project_folder]:
                        scenes_w_missing_static_layers[s3_project_folder].append(scene)

                # get the existing burst products that are missing from the open data cube
                # to be sent to indexing pipelines - ONLY AVAILABLE IN BURST REPORTS
                for burst in report_data["results"]["burst_products_existing_to_index"]:
                    if s3_project_folder not in burst_products_to_index.keys():
                        burst_products_to_index[s3_project_folder] = []
                    if burst not in burst_products_to_index[s3_project_folder]:
                        # get the s3 folder containing the stac item
                        burst_product_folder = report_data["results"][
                            "burst_products_existing_to_index"
                        ][burst]["expected_s3_product_folder"]
                        burst_products_to_index[s3_project_folder].append(
                            burst_product_folder
                        )

    # log the findings
    for s3_project_folder in s3_project_folders:
        if s3_project_folder in scenes_to_reprocess.keys():
            n_scenes_to_reprocess = len(scenes_to_reprocess[s3_project_folder])
        else:
            n_scenes_to_reprocess = 0

        # the following will be empty lists for scene reports
        if s3_project_folder in scenes_w_missing_static_layers.keys():
            n_scenes_w_missing_static_layers = len(
                scenes_w_missing_static_layers[s3_project_folder]
            )
        else:
            n_scenes_w_missing_static_layers = 0

        if s3_project_folder in burst_products_to_index.keys():
            n_burst_products_to_index = len(burst_products_to_index[s3_project_folder])
        else:
            n_burst_products_to_index = 0

        logger.info(
            f"{n_scenes_to_reprocess} unique scene/s found to reprocess "
            f" for s3_project_folder : {s3_project_folder}"
        )
        logger.info(
            f"{n_scenes_w_missing_static_layers} unique scene/s are found"
            f" with missing static layers for s3_project_folder : {s3_project_folder}"
        )
        logger.info(
            f"{n_burst_products_to_index} unique burst products exist "
            f"but are not indexed in the open data cube (ODC) for s3_project_folder : {s3_project_folder}"
        )

    logger.info("Generating SQS messages")
    if dry_run:
        logging.warning(
            f"dry_run, jobs will not be sent to s1-nrb sqs queue : {s1_nrb_sqs_url}"
        )
        if report_type == "burst":
            logging.warning(
                f"dry_run, jobs will not be sent to s1-nrb-static sqs queue : {s1_nrb_sqs_url}"
            )
            logging.warning(
                f"dry_run, jobs will not be sent to odc-indexing queue : {s1_nrb_indexing_sqs_url}"
            )
    else:
        logging.info(f"Adding jobs to s1-nrb sqs queue : {s1_nrb_sqs_url}")

    n_s1_nrb_messages = 0
    n_s1_nrb_static_messages = 0
    n_reindex_messages = 0

    for s3_project_folder in s3_project_folders:
        # send nrb messages to reprocess
        if s3_project_folder in scenes_to_reprocess.keys():
            for scene in scenes_to_reprocess[s3_project_folder]:
                # see example message in ./sqs_message_examples
                start_date = scene[17:25]
                product_unique_id = scene[-4:]
                scene_sqs_message = {
                    "jobname": f"{start_date}_{product_unique_id}_reprocess",
                    "sceneId": scene,
                    "project": s3_project_folder,
                }
                n_s1_nrb_messages += 1
                if not dry_run:
                    _send_job_to_sqs(s1_nrb_sqs_url, scene_sqs_message)

        if report_type == "burst":
            # send static layer messages to reprocess
            if s3_project_folder in scenes_w_missing_static_layers.keys():
                for scene in scenes_w_missing_static_layers[s3_project_folder]:
                    # see example message in ./sqs_message_examples
                    start_date = scene[17:25]
                    product_unique_id = scene[-4:]
                    scene_sqs_message = {
                        "jobname": f"{start_date}_{product_unique_id}_reprocess",
                        "sceneId": scene,
                        "project": s3_project_folder,
                    }
                    n_s1_nrb_static_messages += 1
                    if not dry_run:
                        _send_job_to_sqs(s1_nrb_static_sqs_url, scene_sqs_message)

            # send burst products to re-index
            if s3_project_folder in burst_products_to_index.keys():
                for s3_product_folder in burst_products_to_index[s3_project_folder]:
                    # create the wildcard path to stac for indexing. i.e. the stac
                    # file is stored in this project folder
                    index_path = f"{s3_product_folder}/*stac.json"
                    # TODO format the correct sqs message for indexing
                    product_reindex_message = None
                    n_reindex_messages += 1
                    if not dry_run:
                        _send_job_to_sqs(
                            s1_nrb_indexing_sqs_url, product_reindex_message
                        )

    if not dry_run:
        logging.info(
            f"{n_s1_nrb_messages} scene/s successfully sent to reprocessing s1-nrb sqs queue : {s1_nrb_sqs_url}"
        )
        if report_type == "burst":
            logging.info(
                f"{n_s1_nrb_static_messages} scene/s successfully sent to reprocessing s1-nrb sqs queue : {s1_nrb_static_sqs_url}"
            )
            logging.info(
                f"{n_reindex_messages} burst products successfully sent to odc-indexing sqs queue : {s1_nrb_indexing_sqs_url}"
            )

    else:
        logging.info(
            f"dry_run, {n_s1_nrb_messages} message/s prepared but not sent to s1-nrb sqs queue : {s1_nrb_sqs_url}"
        )
        if report_type == "burst":
            logging.info(
                f"dry_run, {n_s1_nrb_static_messages} message/s prepared but not sent to s1-nrb-static sqs queue : {s1_nrb_static_sqs_url}"
            )
            logging.info(
                f"dry_run, {n_reindex_messages} message/s prepared but not sent to odc-indexing sqs queue : {s1_nrb_indexing_sqs_url}"
            )

    already_resubmitted_jobs = {s3_folder: [] for s3_folder in s3_project_folders}
    jobs_remaining_on_dlq = {s3_folder: [] for s3_folder in s3_project_folders}
    n_dlq_messages_processed = 0

    if remove_resubmitted_scenes_from_dlq:
        logging.info(
            f"Checking the s1-nrb-dlq (dead letter queue) to remove jobs that have been re-submitted by this workflow"
        )
        if dry_run:
            logging.info(
                f"dry_run, messages will not be removed from s1-nrb-dlq: {s1_nrb_dlq_sqs_url}"
            )
        logging.info(
            f"Getting estimated number of messages from dlq : {s1_nrb_dlq_sqs_url}"
        )
        dlq_message_count = _get_estimated_count_of_sqs_messages(s1_nrb_dlq_sqs_url)
        logging.info(f"Estimated count of failed jobs on dlq : {dlq_message_count}")
        logging.info(f"Iterating through messages...")
        while True:
            messages = _read_sqs_messages(s1_nrb_dlq_sqs_url)

            if not messages:
                logging.info(f"All messages processed.")
                break

            for msg in messages:
                n_dlq_messages_processed += 1
                message_body = json.loads(msg["Body"])
                dlq_failed_jobname = message_body["jobname"]
                dlq_failed_scene = message_body["sceneId"]
                dlq_failed_s3_folder = message_body["project"]

                if dlq_failed_s3_folder not in s3_project_folders:
                    # This was not in our reprocess list, leave it on the dlq for manual re-submission
                    jobs_remaining_on_dlq.setdefault(dlq_failed_s3_folder, []).append(
                        dlq_failed_scene
                    )

                elif dlq_failed_scene not in scenes_to_reprocess[dlq_failed_s3_folder]:
                    # This was not in our reprocess list, leave it on the dlq for manual re-submission
                    jobs_remaining_on_dlq[dlq_failed_s3_folder].append(dlq_failed_scene)

                else:
                    # job has been resubmitted and can be removed from the dlq
                    already_resubmitted_jobs[dlq_failed_s3_folder].append(
                        dlq_failed_scene
                    )

                    if not dry_run:
                        # delete after processing
                        sqs = boto3.client("sqs")
                        sqs.delete_message(
                            QueueUrl=s1_nrb_dlq_sqs_url,
                            ReceiptHandle=msg["ReceiptHandle"],
                        )

        # log the dead-letter queue information
        if n_dlq_messages_processed == 0:
            logger.info(
                f"No failed jobs found on the dead-letter queue : : {s1_nrb_dlq_sqs_url}"
            )
        else:
            for s3_project_folder in already_resubmitted_jobs.keys():
                n_resubmitted_jobs = len(already_resubmitted_jobs[s3_project_folder])
                logger.info(
                    f"{n_resubmitted_jobs} failed jobs have already been submitted and have been removed "
                    "from the s1-nrb-dlq"
                )
            for s3_project_folder in jobs_remaining_on_dlq.keys():
                n_jobs_still_remaining_on_dlq = len(
                    jobs_remaining_on_dlq[s3_project_folder]
                )
                logger.warning(
                    f"{n_jobs_still_remaining_on_dlq} failed jobs still remain on the dlq. These were not identified "
                    "in the completeness report and need to be manually re-driven"
                )
            if dry_run:
                logging.info(
                    f"dry_run, messages not actually removed from s1-nrb-dlq: {s1_nrb_dlq_sqs_url}"
                )
