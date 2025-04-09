import pytest

from sar_pipeline.nci.processing.pyroSAR.pyrosar_geocode import prepare_directories


def test_prepare_directories(tmp_path):

    scene_dir = tmp_path / "data/processed_scene/S1_full_name"
    temp_dir = tmp_path / "data/temp/S1_outname"
    log_dir = tmp_path / "data/temp/S1_outname/logfiles"

    processing_directories = prepare_directories(tmp_path, "S1_full_name", "S1_outname")

    # Check paths
    assert processing_directories["scene"] == scene_dir
    assert processing_directories["temp"] == temp_dir
    assert processing_directories["logs"] == log_dir

    # Check paths were created by function
    assert scene_dir.exists()
    assert temp_dir.exists()
    assert log_dir.exists()
