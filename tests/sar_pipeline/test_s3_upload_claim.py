"""Offline tests for the S3 upload claim that stops concurrent runs from
interleaving uploads to the same burst product.

These use botocore's Stubber, so they check the requests sent and the handling
of each response. They cannot prove that S3 itself enforces If-None-Match /
If-Match, or how a real race between two writers resolves.
"""

from datetime import datetime, timedelta, timezone
import json
from unittest import mock

import boto3
from botocore.exceptions import ClientError
from botocore.stub import ANY, Stubber
import pytest

from sar_pipeline.pipelines.isce3_rtc import cli
from sar_pipeline.utils.aws import S3Util, make_upload_claim_key

BUCKET = "bucket"
PROJECT = "baseline"
PRODUCT_FOLDER = (
    "baseline/ga_s1_nrb_iw_vv_vh_1/t070_149815_iw3/2022/01/01/20220101T124745"
)
CLAIM_KEY = (
    "baseline/monitoring/upload_claims/"
    "ga_s1_nrb_iw_vv_vh_1/t070_149815_iw3/2022/01/01/20220101T124745.json"
)
OWNER = {"scene": "S1A_TEST", "hostname": "host", "pid": 1}
STALE_AFTER = 7200


@pytest.fixture
def s3util(monkeypatch):
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    monkeypatch.setenv("AWS_DEFAULT_REGION", "ap-southeast-2")
    util = S3Util()
    util.s3 = boto3.client("s3", region_name="ap-southeast-2")
    return util


def _put_params(**conditional):
    return {
        "Bucket": BUCKET,
        "Key": CLAIM_KEY,
        "Body": ANY,
        "ContentType": "application/json",
        **conditional,
    }


def _head_params():
    return {"Bucket": BUCKET, "Key": CLAIM_KEY}


def _head_response(age_seconds, etag='"old"'):
    return {
        "ETag": etag,
        "LastModified": datetime.now(timezone.utc) - timedelta(seconds=age_seconds),
    }


def test_claim_key_is_outside_product_folder():
    assert make_upload_claim_key(PROJECT, PRODUCT_FOLDER) == CLAIM_KEY
    # a trailing slash on the product folder gives the same key
    assert make_upload_claim_key(PROJECT, PRODUCT_FOLDER + "/") == CLAIM_KEY
    assert not CLAIM_KEY.startswith(PRODUCT_FOLDER)


def test_acquire_new_claim(s3util):
    with Stubber(s3util.s3) as stub:
        stub.add_response(
            "put_object", {"ETag": '"new"'}, _put_params(IfNoneMatch="*")
        )
        etag = s3util.acquire_upload_claim(BUCKET, CLAIM_KEY, OWNER, STALE_AFTER)
        stub.assert_no_pending_responses()
    assert etag == '"new"'


def test_claim_body_records_owner(s3util):
    s3util.s3 = mock.Mock()
    s3util.s3.put_object.return_value = {"ETag": '"new"'}
    s3util.acquire_upload_claim(BUCKET, CLAIM_KEY, OWNER, STALE_AFTER)
    body = json.loads(s3util.s3.put_object.call_args.kwargs["Body"])
    assert body["scene"] == "S1A_TEST"
    assert "claimed_at" in body


def test_fresh_claim_held_by_other_run(s3util):
    with Stubber(s3util.s3) as stub:
        stub.add_client_error(
            "put_object",
            service_error_code="PreconditionFailed",
            http_status_code=412,
            expected_params=_put_params(IfNoneMatch="*"),
        )
        stub.add_response("head_object", _head_response(60), _head_params())
        # no takeover put is queued: the stubber fails if one is attempted
        etag = s3util.acquire_upload_claim(BUCKET, CLAIM_KEY, OWNER, STALE_AFTER)
        stub.assert_no_pending_responses()
    assert etag is None


def test_concurrent_create_conflict_is_treated_as_held(s3util):
    with Stubber(s3util.s3) as stub:
        stub.add_client_error(
            "put_object",
            service_error_code="ConditionalRequestConflict",
            http_status_code=409,
            expected_params=_put_params(IfNoneMatch="*"),
        )
        stub.add_response("head_object", _head_response(1), _head_params())
        etag = s3util.acquire_upload_claim(BUCKET, CLAIM_KEY, OWNER, STALE_AFTER)
    assert etag is None


def test_stale_claim_is_taken_over_with_if_match(s3util):
    with Stubber(s3util.s3) as stub:
        stub.add_client_error(
            "put_object",
            service_error_code="PreconditionFailed",
            http_status_code=412,
            expected_params=_put_params(IfNoneMatch="*"),
        )
        stub.add_response(
            "head_object", _head_response(STALE_AFTER + 60), _head_params()
        )
        stub.add_response(
            "put_object", {"ETag": '"mine"'}, _put_params(IfMatch='"old"')
        )
        etag = s3util.acquire_upload_claim(BUCKET, CLAIM_KEY, OWNER, STALE_AFTER)
        stub.assert_no_pending_responses()
    assert etag == '"mine"'


def test_stale_takeover_lost_to_another_run(s3util):
    with Stubber(s3util.s3) as stub:
        stub.add_client_error(
            "put_object",
            service_error_code="PreconditionFailed",
            http_status_code=412,
            expected_params=_put_params(IfNoneMatch="*"),
        )
        stub.add_response(
            "head_object", _head_response(STALE_AFTER + 60), _head_params()
        )
        stub.add_client_error(
            "put_object",
            service_error_code="PreconditionFailed",
            http_status_code=412,
            expected_params=_put_params(IfMatch='"old"'),
        )
        etag = s3util.acquire_upload_claim(BUCKET, CLAIM_KEY, OWNER, STALE_AFTER)
        stub.assert_no_pending_responses()
    assert etag is None


def test_claim_released_while_checking_is_retried(s3util):
    with Stubber(s3util.s3) as stub:
        stub.add_client_error(
            "put_object",
            service_error_code="PreconditionFailed",
            http_status_code=412,
            expected_params=_put_params(IfNoneMatch="*"),
        )
        stub.add_client_error(
            "head_object",
            service_error_code="404",
            http_status_code=404,
            expected_params=_head_params(),
        )
        stub.add_response(
            "put_object", {"ETag": '"new"'}, _put_params(IfNoneMatch="*")
        )
        etag = s3util.acquire_upload_claim(BUCKET, CLAIM_KEY, OWNER, STALE_AFTER)
        stub.assert_no_pending_responses()
    assert etag == '"new"'


def test_unrelated_error_propagates(s3util):
    with Stubber(s3util.s3) as stub:
        stub.add_client_error(
            "put_object",
            service_error_code="AccessDenied",
            http_status_code=403,
            expected_params=_put_params(IfNoneMatch="*"),
        )
        with pytest.raises(ClientError):
            s3util.acquire_upload_claim(BUCKET, CLAIM_KEY, OWNER, STALE_AFTER)


def test_release_deletes_own_claim(s3util):
    with Stubber(s3util.s3) as stub:
        stub.add_response("head_object", {"ETag": '"mine"'}, _head_params())
        stub.add_response("delete_object", {}, _head_params())
        s3util.release_upload_claim(BUCKET, CLAIM_KEY, '"mine"')
        stub.assert_no_pending_responses()


def test_release_leaves_claim_taken_over_by_other_run(s3util):
    with Stubber(s3util.s3) as stub:
        stub.add_response("head_object", {"ETag": '"theirs"'}, _head_params())
        # no delete queued: the stubber fails if one is attempted
        s3util.release_upload_claim(BUCKET, CLAIM_KEY, '"mine"')
        stub.assert_no_pending_responses()


def test_release_errors_are_not_raised(s3util):
    with Stubber(s3util.s3) as stub:
        stub.add_client_error(
            "head_object", service_error_code="403", http_status_code=403
        )
        s3util.release_upload_claim(BUCKET, CLAIM_KEY, '"mine"')


# -- CLI decision logic ------------------------------------------------------


def _uploader(claim_etag='"mine"'):
    uploader = mock.Mock(spec=S3Util)
    uploader.acquire_upload_claim.return_value = claim_etag
    return uploader


def _run_helper(uploader, tmp_path, marker_exists, make_existing_products=False):
    marker = cli.PRODUCT_COMMIT_MARKER_SUFFIX
    found = [f"{PRODUCT_FOLDER}/x{marker}"] if marker_exists else []
    with mock.patch.object(
        cli, "find_s3_filepaths_from_suffixes", return_value={marker: found}
    ) as find:
        uploaded = cli.upload_burst_product_with_claim(
            s3_uploader=uploader,
            burst_folder=tmp_path,
            s3_bucket=BUCKET,
            s3_project_folder=PROJECT,
            s3_product_folder=PRODUCT_FOLDER,
            scene="S1A_TEST",
            make_existing_products=make_existing_products,
            stale_after_seconds=STALE_AFTER,
        )
    return uploaded, find


def test_helper_uploads_and_releases_when_claim_acquired(tmp_path):
    uploader = _uploader()
    uploaded, _ = _run_helper(uploader, tmp_path, marker_exists=False)
    assert uploaded
    uploader.acquire_upload_claim.assert_called_once()
    assert uploader.acquire_upload_claim.call_args.args[1] == CLAIM_KEY
    push = uploader.push_files_in_folder_to_s3
    push.assert_called_once()
    assert push.call_args.kwargs["last_suffixes"] == cli.UPLOAD_LAST_SUFFIXES
    uploader.release_upload_claim.assert_called_once_with(BUCKET, CLAIM_KEY, '"mine"')


def test_helper_skips_when_claim_held(tmp_path):
    uploader = _uploader(claim_etag=None)
    uploaded, find = _run_helper(uploader, tmp_path, marker_exists=False)
    assert not uploaded
    uploader.push_files_in_folder_to_s3.assert_not_called()
    uploader.release_upload_claim.assert_not_called()
    find.assert_not_called()


def test_helper_skips_and_releases_when_product_appeared(tmp_path):
    uploader = _uploader()
    uploaded, _ = _run_helper(uploader, tmp_path, marker_exists=True)
    assert not uploaded
    uploader.push_files_in_folder_to_s3.assert_not_called()
    uploader.release_upload_claim.assert_called_once()


def test_helper_make_existing_products_uploads_over_marker(tmp_path):
    uploader = _uploader()
    uploaded, find = _run_helper(
        uploader, tmp_path, marker_exists=True, make_existing_products=True
    )
    assert uploaded
    find.assert_not_called()
    uploader.push_files_in_folder_to_s3.assert_called_once()


def test_helper_releases_claim_when_upload_fails(tmp_path):
    uploader = _uploader()
    uploader.push_files_in_folder_to_s3.side_effect = RuntimeError("boom")
    with pytest.raises(RuntimeError):
        _run_helper(uploader, tmp_path, marker_exists=False)
    uploader.release_upload_claim.assert_called_once()
