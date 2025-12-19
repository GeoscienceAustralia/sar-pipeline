import click
from datetime import datetime
from pathlib import Path
import logging

from sar_pipeline.pipelines.isce3_rtc.monitoring.generate_s1_iw_completeness_report import (
    make_burst_product_completeness_report,
    make_scene_odc_completeness_report,
)
from sar_pipeline.utils.aws import check_aws_environment_credentials

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@click.command()
@click.option(
    "--s3-bucket",
    required=True,
    type=str,
    help="S3 bucket where the RTC_S1 nrb burst products are stored.",
)
@click.option(
    "--s3-completeness-report-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="S3 folder where the completeness report will be written. The report will have the structure "
    "{s3_bucket}/{s3_report_folder}/{report_time}_{start_time}_{end_time}_scene_completion_report.json "
    "where time is of the format %Y%m%dT%H%M%S, e.g. "
    "20251218T043403_20241214T000000_20241216T000000_completeness_report.json",
)
@click.option(
    "--s3-project-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Project folder in the S3 bucket containing the RTC_S1 nrb burst products.",
)
@click.option(
    "--collection-number",
    required=True,
    type=str,
    help="Collection number of the RTC_S1 product.",
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
    "--geometry",
    required=False,
    type=str,
    help="URL or path to geometry used for STAC searching.",
)
@click.option(
    "--stac-catalog",
    required=True,
    type=str,
    help="STAC catalog URL (e.g. https://earth-search.aws.element84.com/v1).",
)
def make_scene_odc_completeness_report(
    s3_bucket,
    s3_completeness_report_folder,
    s3_project_folder,
    collection_number,
    start_dt,
    end_dt,
    geometry,
    stac_catalog,
):
    # --- Parse datetimes ---
    start_dt = datetime.strptime(start_dt, "%Y-%m-%dT%H:%M:%SZ")
    end_dt = datetime.strptime(end_dt, "%Y-%m-%dT%H:%M:%SZ")

    missing_credentials = check_aws_environment_credentials(verbose=True)
    if missing_credentials:
        logging.warning(
            "AWS credentials are missing. May not be able to publish completion report AWS S3."
        )

    make_scene_odc_completeness_report(
        s3_completeness_report_folder=s3_completeness_report_folder,
        s3_bucket=s3_bucket,
        s3_project_folder=s3_project_folder,
        collection_number=collection_number,
        start_dt=start_dt,
        end_dt=end_dt,
        geometry=geometry,
        stac_catalog=stac_catalog,
    )


@click.command()
@click.option(
    "--s3-bucket",
    required=True,
    type=str,
    help="S3 bucket where the RTC_S1 nrb burst products are stored.",
)
@click.option(
    "--s3-completeness-report-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="S3 folder where the completeness report will be written. The report will have the structure "
    "{s3_bucket}/{s3_report_folder}/{report_time}_{start_time}_{end_time}_burst_completion_report.json "
    "where time is of the format %Y%m%dT%H%M%S, e.g. "
    "20251218T043403_20241214T000000_20241216T000000_completeness_report.json",
)
@click.option(
    "--s3-project-folder",
    required=True,
    type=click.Path(file_okay=False, path_type=Path),
    help="Project folder in the S3 bucket containing the RTC_S1 nrb burst products.",
)
@click.option(
    "--collection-number",
    required=True,
    type=str,
    help="Collection number of the RTC_S1 product.",
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
    "--geometry",
    required=False,
    type=str,
    help="URL or path to geometry used for STAC searching.",
)
@click.option(
    "--stac-catalog",
    required=True,
    type=str,
    help="STAC catalog URL (e.g. https://earth-search.aws.element84.com/v1).",
)
@click.option(
    "--identify-missing-linked-static-layers",
    is_flag=True,
    default=True,
    help="Identify missing linked static layers.",
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
    s3_completeness_report_folder,
    s3_project_folder,
    collection_number,
    start_dt,
    end_dt,
    geometry,
    stac_catalog,
    identify_missing_linked_static_layers,
    dem_type,
    static_layer_validity_start_date,
    linked_static_layer_s3_bucket,
    linked_static_layer_s3_project_folder,
    linked_static_layer_collection_number,
):
    """
    Generate a burst-level completeness report for RTC_S1 products.
    """

    # --- Parse datetimes ---
    start_dt = datetime.strptime(start_dt, "%Y-%m-%dT%H:%M:%SZ")
    end_dt = datetime.strptime(end_dt, "%Y-%m-%dT%H:%M:%SZ")

    # --- Default linked static layer bucket ---
    if identify_missing_linked_static_layers is None:
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

    missing_credentials = check_aws_environment_credentials(verbose=True)
    if missing_credentials:
        logging.warning(
            "AWS credentials are missing. May not be able to publish completion report AWS S3."
        )

    make_burst_product_completeness_report(
        s3_completeness_report_folder=s3_completeness_report_folder,
        s3_bucket=s3_bucket,
        s3_project_folder=s3_project_folder,
        collection_number=collection_number,
        start_dt=start_dt,
        end_dt=end_dt,
        geometry=geometry,
        stac_catalog=stac_catalog,
        identify_missing_linked_static_layers=identify_missing_linked_static_layers,
        dem_type=dem_type,
        static_layer_validity_start_date=static_layer_validity_start_date,
        linked_static_layer_s3_bucket=linked_static_layer_s3_bucket,
        linked_static_layer_s3_project_folder=linked_static_layer_s3_project_folder,
        linked_static_layer_collection_number=linked_static_layer_collection_number,
    )
