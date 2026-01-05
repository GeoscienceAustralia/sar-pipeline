import click
from datetime import datetime
from pathlib import Path
import logging

from sar_pipeline.pipelines.isce3_rtc.monitoring.generate_s1_iw_completeness_report import (
    make_burst_product_completeness_report,
    make_scene_completeness_report,
)
from sar_pipeline.utils.aws import check_aws_environment_credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--s3-bucket",
    required=True,
    type=str,
    help="S3 bucket where the burst products are stored.",
)
@click.option(
    "--s3-project-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Project folder in the S3 bucket containing the burst products.",
)
@click.option(
    "--collection-number",
    required=True,
    type=str,
    help="Collection number of the products.",
)
@click.option(
    "--start-dt",
    required=True,
    type=str,
    help="Start datetime (ISO format, e.g. 2024-01-01T00:00:00Z).",
)
@click.option(
    "--end-dt",
    required=True,
    type=str,
    help="End datetime (ISO format, e.g. 2024-01-31T23:59:59Z).",
)
@click.option(
    "--roi-geojson",
    required=False,
    type=str,
    help="URL or path to geometry with region of interest for scenes.",
)
@click.option(
    "--stac-catalog",
    # required=True,
    default="https://explorer.dev.dea.ga.gov.au/stac",
    type=str,
    help="STAC catalog URL (e.g. https://explorer.dev.dea.ga.gov.au/stac).",
)
@click.option(
    "--s3-completeness-report-folder",
    required=False,
    type=click.Path(file_okay=False, path_type=Path),
    help="S3 folder where the completeness report will be written. The report will have the structure "
    "{s3_report_folder}/{report_time}_{start_time}_{end_time}_scene_completion_report.json "
    "where time is of the format %Y%m%dT%H%M%S, e.g. "
    "20251218T043403_20241214T000000_20241216T000000_completeness_report.json. If not provided,"
    "it will be set to {s3_report_folder}/monitoring/completeness_reports by default.",
)
def make_scene_completeness_report_cli(
    s3_bucket,
    s3_project_folder,
    collection_number,
    start_dt,
    end_dt,
    roi_geojson,
    stac_catalog,
    s3_completeness_report_folder,
):
    """
    Generate a scene completeness report for normalised radar backscatter (nrb) products.

    NOTE - The following only considers scenes that have been processed, and not
    individual burst products. For a detailed report, the cli make_burst_product_completeness_report_cli
    should be used.

    First, the CDSE is queried for scene_ids within the provided time range and geometry to get
    an expected list of processed scenes. Next, the function will search the monitoring folder
    for the scene tracking files that get uploaded with every run to:
            - {s3_project_folder}/monitoring/processed_scenes/{scene}.json.

    The list of scenes in this folder is then compared to the list of expected scenes, resulting
    in a list of scenes that have not been processed in the expected time-range. These scenes
    should be re-sent for processing.

    However, if the processed_scenes monitoring folder is empty, a warning is raised and the function
    falls back to querying the the open data cube (odc) via the stac-api to determine the processed
    scenes associated with the burst products. We can then determine if any of the expected scenes are
    missing from the odc (i.e. have no associated burst products). This process is much slower than
    checking the monitoring folder and may not be suitable for large timeframes.

    A completeness report (.json) is created detailing the missing scenes that need reprocessing.
    This report should be monitored by another process.
    """

    # --- Parse datetimes ---
    start_dt = datetime.strptime(start_dt, "%Y-%m-%dT%H:%M:%SZ")
    end_dt = datetime.strptime(end_dt, "%Y-%m-%dT%H:%M:%SZ")

    missing_credentials = check_aws_environment_credentials(verbose=True)
    if missing_credentials:
        logging.warning(
            "AWS credentials are missing. May not be able to publish completion report AWS S3."
        )

    make_scene_completeness_report(
        s3_bucket=s3_bucket,
        s3_project_folder=s3_project_folder,
        collection_number=collection_number,
        start_dt=start_dt,
        end_dt=end_dt,
        roi_geojson=roi_geojson,
        stac_catalog=stac_catalog,
        s3_completeness_report_folder=s3_completeness_report_folder,
    )


@click.command()
@click.option(
    "--s3-bucket",
    required=True,
    type=str,
    help="S3 bucket where the burst products are stored.",
)
@click.option(
    "--s3-project-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Project folder in the S3 bucket containing the burst products.",
)
@click.option(
    "--collection-number",
    required=True,
    type=str,
    help="Collection number of the product.",
)
@click.option(
    "--start-dt",
    required=True,
    type=str,
    help="Start datetime (ISO format, e.g. 2024-01-01T00:00:00Z).",
)
@click.option(
    "--end-dt",
    required=True,
    type=str,
    help="End datetime (ISO format, e.g. 2024-01-31T23:59:59Z).",
)
@click.option(
    "--roi-geojson",
    required=False,
    type=str,
    help="URL or path to geometry with region of interest for bursts.",
)
@click.option(
    "--stac-catalog",
    # required=True,
    default="https://explorer.dev.dea.ga.gov.au/stac",
    type=str,
    help="STAC catalog URL (e.g. https://explorer.dev.dea.ga.gov.au/stac).",
)
@click.option(
    "--s3-completeness-report-folder",
    required=False,
    type=click.Path(file_okay=False, path_type=Path),
    help="S3 folder where the completeness report will be written. The report will have the structure "
    "{s3_report_folder}/{report_time}_{start_time}_{end_time}_scene_completion_report.json "
    "where time is of the format %Y%m%dT%H%M%S, e.g. "
    "20251218T043403_20241214T000000_20241216T000000_completeness_report.json. If not provided,"
    "it will be set to {s3_report_folder}/monitoring/completeness_reports by default.",
)
@click.option(
    "--skip-identify-missing-linked-static-layers",
    is_flag=True,
    default=False,
    help="Skip identification of missing linked static layers.",
)
@click.option(
    "--dem-type",
    default="best",
    type=str,
    help="DEM type to use when resolving static layers.",
)
@click.option(
    "--static-layer-validity-start-date",
    default=20140403,
    type=int,
    help="Static layer validity start date (YYYYMMDD).",
)
@click.option(
    "--linked-static-layer-s3-bucket",
    required=False,
    type=str,
    help="S3 bucket containing linked RTC_S1_STATIC layers. "
    "Defaults to --s3-bucket if not provided.",
)
@click.option(
    "--linked-static-layer-s3-project-folder",
    required=False,
    type=str,
    help="S3 project folder containing linked RTC_S1_STATIC layers.",
)
@click.option(
    "--linked-static-layer-collection-number",
    required=False,
    type=str,
    help="Collection number of linked RTC_S1_STATIC layers.",
)
def make_burst_product_completeness_report_cli(
    s3_bucket,
    s3_project_folder,
    collection_number,
    start_dt,
    end_dt,
    roi_geojson,
    stac_catalog,
    s3_completeness_report_folder,
    skip_identify_missing_linked_static_layers,
    dem_type,
    static_layer_validity_start_date,
    linked_static_layer_s3_bucket,
    linked_static_layer_s3_project_folder,
    linked_static_layer_collection_number,
):
    """
    Generate a burst-level completeness report for normalised radar backscatter (nrb) products.

    NOTE - small windows of <10 days should be used. For larger time spans, the
    make_scene_odc_completeness_report_cli should be used to identify unprocessed
    scenes.

    First, the CDSE burst API is queried for burst_ids and datetimes within the provided
    time range and geometry. We expect to have a RTC_S1/nrb product for each of these
    bursts. Next, the provided AWS S3 bucket is searched to ensure the expected products exist.
    Next, the open data cube (odc) is queried to ensure the expected products are indexed and
    available via the stac api.

    By default, the static layers for the missing scenes will also be searched for, as the nrb
    product may have failed due to a missing static layer. If a large number of nrb products are
    missing, this may take a long time. In this case --skip-identify-missing-linked-static-layers
    should be set.

    A detailed report (.json) is then created detailing the missing bursts, static layers and
    scenes that need either reprocessing, or indexing in to the odc. This report should be
    monitored by another process.
    """

    # --- Parse datetimes ---
    start_dt = datetime.strptime(start_dt, "%Y-%m-%dT%H:%M:%SZ")
    end_dt = datetime.strptime(end_dt, "%Y-%m-%dT%H:%M:%SZ")

    # --- Default linked static layer bucket if not directly set---
    if not skip_identify_missing_linked_static_layers:
        logging.info("Missing static layers will be searched for")
        identify_missing_linked_static_layers = True
        if not linked_static_layer_s3_bucket:
            logger.warning(
                "--linked-static-layer-s3-bucket not provided. Setting to --s3-bucket"
            )
            linked_static_layer_s3_bucket = s3_bucket
        if not linked_static_layer_s3_project_folder:
            logger.warning(
                "--linked-static-layer-s3-project-folder not provided. Setting to --s3-project-folder"
            )
            linked_static_layer_s3_project_folder = s3_project_folder
        if not linked_static_layer_collection_number:
            logger.warning(
                "--linked-static-layer-collection-number not provided. Setting to --collection-number"
            )
            linked_static_layer_s3_project_folder = s3_project_folder
    else:
        logging.info("Missing static layers will be NOT be searched for")
        identify_missing_linked_static_layers = False

    missing_credentials = check_aws_environment_credentials(verbose=True)
    if missing_credentials:
        logging.warning(
            "AWS credentials are missing. May not be able to publish completion report AWS S3."
        )

    make_burst_product_completeness_report(
        s3_bucket=s3_bucket,
        s3_project_folder=s3_project_folder,
        collection_number=collection_number,
        start_dt=start_dt,
        end_dt=end_dt,
        roi_geojson=roi_geojson,
        stac_catalog=stac_catalog,
        s3_completeness_report_folder=s3_completeness_report_folder,
        identify_missing_linked_static_layers=identify_missing_linked_static_layers,
        dem_type=dem_type,
        static_layer_validity_start_date=static_layer_validity_start_date,
        linked_static_layer_s3_bucket=linked_static_layer_s3_bucket,
        linked_static_layer_s3_project_folder=linked_static_layer_s3_project_folder,
        linked_static_layer_collection_number=linked_static_layer_collection_number,
    )
