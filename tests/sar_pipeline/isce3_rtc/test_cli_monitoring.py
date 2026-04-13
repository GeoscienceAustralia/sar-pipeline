from click.testing import CliRunner
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
import logging
import pytest

from sar_pipeline.pipelines.isce3_rtc.monitoring.cli import (
    generate_s1_iw_burst_completeness_report_cli,
    generate_s1_iw_scene_completeness_report_cli,
    process_s1_iw_burst_completeness_report_cli,
    process_s1_iw_scene_completeness_report_cli,
)

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)


@dataclass
class BurstCompletenessConfig:
    s3_bucket: str
    s3_project_folder: str
    collection_number: str
    start_dt: str  # ISO8601, e.g. "2024-12-14T00:00:00Z"
    end_dt: str
    roi_wkt: str | None  # Provide one of roi_wkt or roi_geojson
    roi_geojson: str | None
    stac_catalog: str
    s3_completeness_report_folder: Path | None
    skip_check_indexed_products: bool
    skip_identify_missing_linked_static_layers: bool
    dem_type: str
    static_layer_validity_start_date: int
    linked_static_layer_s3_bucket: str | None
    linked_static_layer_s3_project_folder: str | None
    linked_static_layer_collection_number: str | None
    dry_run: bool


@dataclass
class SceneCompletenessConfig:
    s3_bucket: str
    s3_project_folder: str
    collection_number: str
    start_dt: str
    end_dt: str
    roi_wkt: str | None
    roi_geojson: str | None
    stac_catalog: str
    s3_completeness_report_folder: Path | None
    dry_run: bool


@dataclass
class SceneProcessConfig:
    s3_bucket: str
    s3_completeness_report_folder: str
    s1_nrb_sqs_url: str
    s1_nrb_dlq_sqs_url: Optional[str]
    remove_resubmitted_scenes_from_dlq: bool
    report_name: Optional[str]
    n_most_recent_reports: Optional[int]
    dry_run: bool


@dataclass
class BurstProcessConfig:
    s3_bucket: str
    s3_completeness_report_folder: str
    s1_nrb_sqs_url: str
    s1_nrb_static_sqs_url: str
    s1_nrb_dlq_sqs_url: Optional[str]
    remove_resubmitted_scenes_from_dlq: bool
    re_index_missing_products: bool
    report_name: Optional[str]
    n_most_recent_reports: Optional[int]
    dry_run: bool


GENERATE_BURST_REPORT_TEST_1 = BurstCompletenessConfig(
    s3_bucket="deant-data-public-dev",
    s3_project_folder="experimental/baseline/c1_testing",
    collection_number="1",
    # Keep the window small (< 10 days as per CLI note)
    start_dt="2024-12-14T04:00:00Z",
    end_dt="2024-12-14T08:00:00Z",
    # Provide ROI via WKT (a small polygon) - This is the antarctic ROI
    roi_wkt=(
        "POLYGON ((-179.99 -50, -81 -50, -81 -55, -73 -60, -66 -60, -52 -54, -52 -50, 0 -50, 179.99 -50, 179.99 -90, -179.99 -90, -179.99 -50))"
    ),
    roi_geojson=None,
    # can rely on the CLI default, but pass it explicitly for clarity
    stac_catalog="https://explorer.dev.dea.ga.gov.au/stac",
    # Optional: let CLI apply default report path logic by leaving None
    s3_completeness_report_folder=None,
    # Speed up test and avoid indexing lookups
    skip_check_indexed_products=True,
    skip_identify_missing_linked_static_layers=False,
    dem_type="best",
    static_layer_validity_start_date=20140403,
    # Let CLI default these to the main bucket/folder/collection
    linked_static_layer_s3_bucket=None,
    linked_static_layer_s3_project_folder=None,
    linked_static_layer_collection_number=None,
    # Do not upload to S3 in tests
    dry_run=True,
)

GENERATE_SCENE_REPORT_TEST_1 = SceneCompletenessConfig(
    s3_bucket="deant-data-public-dev",
    s3_project_folder="experimental/baseline/c1_testing",
    collection_number="1",
    start_dt="2024-12-14T04:00:00Z",
    end_dt="2024-12-14T08:00:00Z",
    roi_wkt=(
        "POLYGON ((-179.99 -50, -81 -50, -81 -55, -73 -60, -66 -60, -52 -54, -52 -50, 0 -50, 179.99 -50, 179.99 -90, -179.99 -90, -179.99 -50))"
    ),
    roi_geojson=None,
    stac_catalog="https://explorer.dev.dea.ga.gov.au/stac",
    s3_completeness_report_folder=None,  # let CLI use its default location logic
    dry_run=True,  # generate but do not upload
)

SCENE_TEST_WITH_REPORT = SceneProcessConfig(
    s3_bucket="deant-data-public-dev",
    s3_completeness_report_folder="persistent/repositories/sar-pipeline/tests/sar_pipeline/isce3_rtc/monitoring/scene_completion_reports",
    s1_nrb_sqs_url="https://sqs.ap-southeast-2.amazonaws.com/123456789012/s1-nrb",
    s1_nrb_dlq_sqs_url="https://sqs.ap-southeast-2.amazonaws.com/123456789012/s1-nrb-dlq",
    remove_resubmitted_scenes_from_dlq=False,
    report_name="20260304T020210_20241214T040000_20241214T080000_scene_completeness_report.json",
    n_most_recent_reports=None,
    dry_run=True,
)

SCENE_TEST_WITH_N_MOST_RECENT = SceneProcessConfig(
    s3_bucket="deant-data-public-dev",
    s3_completeness_report_folder="persistent/repositories/sar-pipeline/tests/sar_pipeline/isce3_rtc/monitoring/scene_completion_reports",
    s1_nrb_sqs_url="https://sqs.ap-southeast-2.amazonaws.com/123456789012/s1-nrb",
    s1_nrb_dlq_sqs_url="https://sqs.ap-southeast-2.amazonaws.com/123456789012/s1-nrb-dlq",
    remove_resubmitted_scenes_from_dlq=False,
    report_name=None,
    n_most_recent_reports=2,
    dry_run=True,
)

BURST_TEST_WITH_REPORT = BurstProcessConfig(
    s3_bucket="deant-data-public-dev",
    s3_completeness_report_folder="persistent/repositories/sar-pipeline/tests/sar_pipeline/isce3_rtc/monitoring/burst_completion_reports",
    s1_nrb_sqs_url="https://sqs.ap-southeast-2.amazonaws.com/123456789012/s1-nrb",
    s1_nrb_static_sqs_url="https://sqs.ap-southeast-2.amazonaws.com/123456789012/s1-nrb-static",
    s1_nrb_dlq_sqs_url="https://sqs.ap-southeast-2.amazonaws.com/123456789012/s1-nrb-dlq",
    remove_resubmitted_scenes_from_dlq=False,
    re_index_missing_products=False,
    report_name="20260304T015903_20241214T040000_20241214T080000_burst_completeness_report.json",
    n_most_recent_reports=None,
    dry_run=True,
)

BURST_TEST_WITH_N_MOST_RECENT = BurstProcessConfig(
    s3_bucket="deant-data-public-dev",
    s3_completeness_report_folder="persistent/repositories/sar-pipeline/tests/sar_pipeline/isce3_rtc/monitoring/burst_completion_reports",
    s1_nrb_sqs_url="https://sqs.ap-southeast-2.amazonaws.com/123456789012/s1-nrb",
    s1_nrb_static_sqs_url="https://sqs.ap-southeast-2.amazonaws.com/123456789012/s1-nrb-static",
    s1_nrb_dlq_sqs_url="https://sqs.ap-southeast-2.amazonaws.com/123456789012/s1-nrb-dlq",
    remove_resubmitted_scenes_from_dlq=False,
    re_index_missing_products=False,
    report_name=None,
    n_most_recent_reports=3,
    dry_run=True,
)


@pytest.mark.parametrize("test_run", [GENERATE_BURST_REPORT_TEST_1])
def test_generate_s1_iw_burst_completeness_report_cli(
    test_run: BurstCompletenessConfig,
):
    runner = CliRunner()

    args: list[str] = []
    args += ["--s3-bucket", test_run.s3_bucket]
    args += ["--s3-project-folder", test_run.s3_project_folder]
    args += ["--collection-number", test_run.collection_number]
    args += ["--start-dt", test_run.start_dt]
    args += ["--end-dt", test_run.end_dt]

    # Provide ROI via WKT or GeoJSON
    if test_run.roi_wkt:
        args += ["--roi-wkt", test_run.roi_wkt]
    elif test_run.roi_geojson:
        args += ["--roi-geojson", test_run.roi_geojson]

    if test_run.stac_catalog:
        args += ["--stac-catalog", test_run.stac_catalog]

    if test_run.s3_completeness_report_folder:
        args += [
            "--s3-completeness-report-folder",
            str(test_run.s3_completeness_report_folder),
        ]

    if test_run.skip_check_indexed_products:
        args += ["--skip-check-indexed-products"]
    if test_run.skip_identify_missing_linked_static_layers:
        args += ["--skip-identify-missing-linked-static-layers"]

    args += ["--dem-type", test_run.dem_type]
    args += [
        "--static-layer-validity-start-date",
        str(test_run.static_layer_validity_start_date),
    ]

    # Linked static layer options (only pass if explicitly set)
    if test_run.linked_static_layer_s3_bucket:
        args += [
            "--linked-static-layer-s3-bucket",
            test_run.linked_static_layer_s3_bucket,
        ]
    if test_run.linked_static_layer_s3_project_folder:
        args += [
            "--linked-static-layer-s3-project-folder",
            test_run.linked_static_layer_s3_project_folder,
        ]
    if test_run.linked_static_layer_collection_number:
        args += [
            "--linked-static-layer-collection-number",
            test_run.linked_static_layer_collection_number,
        ]

    # Dry run to avoid uploads
    if test_run.dry_run:
        args += ["--dry-run"]

    logging.info("Running burst completeness CLI.")
    result = runner.invoke(
        generate_s1_iw_burst_completeness_report_cli, args, catch_exceptions=False
    )

    if result.exception:
        logging.exception(
            "An error occurred during CLI invocation", exc_info=result.exception
        )
        logging.error(result.output)

    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("test_run", [GENERATE_SCENE_REPORT_TEST_1])
def test_generate_s1_iw_scene_completeness_report_cli(
    test_run: SceneCompletenessConfig,
):
    runner = CliRunner()

    args: list[str] = []
    args += ["--s3-bucket", test_run.s3_bucket]
    args += ["--s3-project-folder", test_run.s3_project_folder]
    args += ["--collection-number", test_run.collection_number]
    args += ["--start-dt", test_run.start_dt]
    args += ["--end-dt", test_run.end_dt]

    # Provide ROI via WKT or GeoJSON
    if test_run.roi_wkt:
        args += ["--roi-wkt", test_run.roi_wkt]
    elif test_run.roi_geojson:
        args += ["--roi-geojson", test_run.roi_geojson]

    if test_run.stac_catalog:
        args += ["--stac-catalog", test_run.stac_catalog]

    if test_run.s3_completeness_report_folder:
        args += [
            "--s3-completeness-report-folder",
            str(test_run.s3_completeness_report_folder),
        ]

    # Dry run to avoid uploads
    if test_run.dry_run:
        args += ["--dry-run"]

    logging.info("Running scene completeness CLI.")
    result = runner.invoke(
        generate_s1_iw_scene_completeness_report_cli, args, catch_exceptions=False
    )

    if result.exception:
        logging.exception(
            "An error occurred during CLI invocation", exc_info=result.exception
        )
        logging.error(result.output)

    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("cfg", [SCENE_TEST_WITH_REPORT, SCENE_TEST_WITH_N_MOST_RECENT])
def test_process_s1_iw_scene_report_cli(cfg: SceneProcessConfig):

    args = []
    args += ["--s3-bucket", cfg.s3_bucket]
    args += ["--s3-completeness-report-folder", cfg.s3_completeness_report_folder]
    args += ["--s1-nrb-sqs-url", cfg.s1_nrb_sqs_url]
    if cfg.s1_nrb_dlq_sqs_url:
        args += ["--s1-nrb-dlq-sqs-url", cfg.s1_nrb_dlq_sqs_url]
    if cfg.remove_resubmitted_scenes_from_dlq:
        args += ["--remove-resubmitted-scenes-from-dlq"]
    if cfg.report_name:
        args += ["--report-name", cfg.report_name]
    if cfg.n_most_recent_reports is not None:
        args += ["--n-most-recent-reports", str(cfg.n_most_recent_reports)]
    if cfg.dry_run:
        args += ["--dry-run"]

    runner = CliRunner()
    result = runner.invoke(
        process_s1_iw_scene_completeness_report_cli,
        args,
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output


@pytest.mark.parametrize("cfg", [BURST_TEST_WITH_REPORT, BURST_TEST_WITH_N_MOST_RECENT])
def test_process_s1_iw_burst_report_cli(cfg: BurstProcessConfig):

    args = []
    args += ["--s3-bucket", cfg.s3_bucket]
    args += ["--s3-completeness-report-folder", cfg.s3_completeness_report_folder]
    args += ["--s1-nrb-sqs-url", cfg.s1_nrb_sqs_url]
    args += ["--s1-nrb-static-sqs-url", cfg.s1_nrb_static_sqs_url]
    if cfg.s1_nrb_dlq_sqs_url:
        args += ["--s1-nrb-dlq-sqs-url", cfg.s1_nrb_dlq_sqs_url]
    if cfg.remove_resubmitted_scenes_from_dlq:
        args += ["--remove-resubmitted-scenes-from-dlq"]
    if cfg.re_index_missing_products:
        args += ["--re-index-missing-products"]
    if cfg.report_name:
        args += ["--report-name", cfg.report_name]
    if cfg.n_most_recent_reports is not None:
        args += ["--n-most-recent-reports", str(cfg.n_most_recent_reports)]
    if cfg.dry_run:
        args += ["--dry-run"]

    runner = CliRunner()
    result = runner.invoke(
        process_s1_iw_burst_completeness_report_cli,
        args,
        catch_exceptions=False,
    )

    assert result.exit_code == 0, result.output
