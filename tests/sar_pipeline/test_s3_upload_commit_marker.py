"""Offline tests for the product commit marker: upload order and the
existence check that relies on it."""

from datetime import datetime
from unittest import mock

import pytest

from sar_pipeline.pipelines.isce3_rtc.metadata.filetypes import (
    PRODUCT_COMMIT_MARKER_SUFFIX,
    UPLOAD_LAST_SUFFIXES,
)
from sar_pipeline.pipelines.isce3_rtc.utils import burst_utils
from sar_pipeline.utils.aws import S3Util

PRODUCT = "ga_s1_nrb_iw_vv_vh_1-0-0_t070-149815-iw3_20220101T124745"
PRODUCT_FILES = [
    f"{PRODUCT}_stac-item.json",
    f"{PRODUCT}_metadata.h5",
    f"{PRODUCT}_VV-gamma0.tif",
    f"{PRODUCT}_VH-gamma0.tif",
    f"{PRODUCT}_mask.tif",
    f"{PRODUCT}_thumbnail.png",
    f"{PRODUCT}_checksum.sha1",
    f"{PRODUCT}_metadata.xml",
    f"{PRODUCT}_proc-config.yaml",
]


@pytest.fixture
def fake_aws_env(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-2")


@pytest.fixture
def product_folder(tmp_path):
    folder = tmp_path / "t070_149815_iw3"
    folder.mkdir()
    for name in PRODUCT_FILES:
        (folder / name).write_text("x")
    return folder


def _uploaded_names(s3_mock):
    return [c.args[2].split("/")[-1] for c in s3_mock.upload_file.call_args_list]


def test_marker_constants():
    assert PRODUCT_COMMIT_MARKER_SUFFIX == "_stac-item.json"
    assert UPLOAD_LAST_SUFFIXES[-1] == PRODUCT_COMMIT_MARKER_SUFFIX


def test_upload_puts_h5_then_stac_item_last(fake_aws_env, product_folder):
    uploader = S3Util()
    uploader.s3 = mock.Mock()

    uploader.push_files_in_folder_to_s3(
        product_folder, "bucket", "prefix/burst", last_suffixes=UPLOAD_LAST_SUFFIXES
    )

    names = _uploaded_names(uploader.s3)
    assert sorted(names) == sorted(PRODUCT_FILES)  # each file exactly once
    assert names[-1] == f"{PRODUCT}_stac-item.json"
    assert names[-2] == f"{PRODUCT}_metadata.h5"
    keys = [c.args[2] for c in uploader.s3.upload_file.call_args_list]
    assert all(k.startswith("prefix/burst/") for k in keys)


def test_upload_without_last_suffixes_uploads_everything(fake_aws_env, product_folder):
    uploader = S3Util()
    uploader.s3 = mock.Mock()

    uploader.push_files_in_folder_to_s3(product_folder, "bucket", "prefix/burst")

    assert sorted(_uploaded_names(uploader.s3)) == sorted(PRODUCT_FILES)


def test_upload_respects_excludes_with_last_suffixes(fake_aws_env, product_folder):
    uploader = S3Util()
    uploader.s3 = mock.Mock()

    uploader.push_files_in_folder_to_s3(
        product_folder,
        "bucket",
        "prefix/burst",
        exclude_extensions=[".h5"],
        last_suffixes=UPLOAD_LAST_SUFFIXES,
    )

    names = _uploaded_names(uploader.s3)
    assert f"{PRODUCT}_metadata.h5" not in names
    assert names[-1] == f"{PRODUCT}_stac-item.json"


def _fake_find(existing: dict[str, list[str]]):
    """Return a fake find_s3_filepaths_from_suffixes. `existing` maps an s3
    folder substring (the burst id) to the file names in that folder."""

    def _find(bucket_name, s3_folder, suffixes, warn_credentials=True):
        files = []
        for burst_id, names in existing.items():
            if burst_id in s3_folder:
                files = [f"{s3_folder}/{n}" for n in names]
        return {s: [f for f in files if f.endswith(s)] for s in suffixes}

    return _find


def _check(existing, burst_ids, **kwargs):
    with mock.patch.object(
        burst_utils, "find_s3_filepaths_from_suffixes", _fake_find(existing)
    ):
        return burst_utils.check_burst_product_h5_exists_in_s3(
            product="RTC_S1",
            burst_id_list=burst_ids,
            burst_st_list=[datetime(2022, 1, 1, 12, 47, 45)] * len(burst_ids),
            burst_polarisations=["VV", "VH"],
            s3_bucket="bucket",
            s3_project_folder="baseline",
            collection_number=1,
            dem_type="cop_glo30",
            static_layer_validity_start_date=20140403,
            **kwargs,
        )


def test_existence_check_skips_bursts_with_marker():
    existing = {"t070_149815_iw3": PRODUCT_FILES}
    to_process = _check(existing, ["t070_149815_iw2", "t070_149815_iw3"])
    assert to_process == ["t070_149815_iw2"]


def test_existence_check_treats_h5_without_marker_as_missing():
    # legacy partial upload: the .h5 and some tifs landed, the stac item did not
    partial = [f for f in PRODUCT_FILES if not f.endswith("_stac-item.json")]
    existing = {"t070_149815_iw3": partial}
    to_process = _check(existing, ["t070_149815_iw2", "t070_149815_iw3"])
    assert to_process == ["t070_149815_iw2", "t070_149815_iw3"]


def test_existence_check_early_exits_when_all_markers_exist():
    existing = {
        "t070_149815_iw2": PRODUCT_FILES,
        "t070_149815_iw3": PRODUCT_FILES,
    }
    with pytest.raises(SystemExit) as e:
        _check(existing, ["t070_149815_iw2", "t070_149815_iw3"])
    assert e.value.code == 100


def test_existence_check_make_existing_products_processes_all():
    existing = {"t070_149815_iw3": PRODUCT_FILES}
    to_process = _check(
        existing,
        ["t070_149815_iw2", "t070_149815_iw3"],
        make_existing_products=True,
    )
    assert to_process == ["t070_149815_iw2", "t070_149815_iw3"]
