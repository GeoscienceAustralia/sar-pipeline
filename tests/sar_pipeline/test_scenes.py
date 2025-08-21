import datetime
from sar_pipeline.preparation.nci.scenes import (
    parse_scene_file_dates,
    parse_scene_file_sensor,
)
from sar_pipeline.aws.preparation.scenes import (
    query_scene_from_asf,
    query_scene_from_cdse,
)
from sar_pipeline.utils.sentinel1 import (
    is_s1_filename,
    is_s1_id,
    extract_metadata_from_s1_id,
)

import dataclasses
from datetime import datetime
from pathlib import Path
import pytest


@dataclasses.dataclass
class Scene:
    id: str
    mission: str
    beam_mode: str
    product_type: str
    resolution_class: str
    processing_level: str
    product_class: str
    polarisation: str
    start_date: str
    stop_date: str
    absolute_orbit_number: str
    mission_data_take: str
    product_uid: str

    @property
    def start_date_datetime(self) -> datetime:
        return datetime.strptime(self.start_date, "%Y%m%dT%H%M%S")

    @property
    def stop_date_datetime(self) -> datetime:
        return datetime.strptime(self.stop_date, "%Y%m%dT%H%M%S")


scene_1 = Scene(
    id="S1A_EW_GRDM_1SDH_20200330T165825_20200330T165929_031907_03AF02_8570",
    mission="S1A",
    beam_mode="EW",
    product_type="GRD",
    resolution_class="M",
    processing_level="1",
    product_class="S",
    polarisation="DH",
    start_date="20200330T165825",
    stop_date="20200330T165929",
    absolute_orbit_number="031907",
    mission_data_take="03AF02",
    product_uid="8570",
)

scene_2 = Scene(
    id="S1B_EW_GRDM_1SDH_20210914T112333_20210914T112403_028693_036C96_3EA8",
    mission="S1B",
    beam_mode="EW",
    product_type="GRD",
    resolution_class="M",
    processing_level="1",
    product_class="S",
    polarisation="DH",
    start_date="20210914T112333",
    stop_date="20210914T112403",
    absolute_orbit_number="028693",
    mission_data_take="036C96",
    product_uid="3EA8",
)

scene_3 = Scene(
    id="S1B_IW_SLC__1SSH_20211216T123605_20211216T123634_030050_03968D_9501",
    mission="S1B",
    beam_mode="IW",
    product_type="SLC",
    resolution_class="_",
    processing_level="1",
    product_class="S",
    polarisation="SH",
    start_date="20211216T123605",
    stop_date="20211216T123634",
    absolute_orbit_number="030050",
    mission_data_take="03968D",
    product_uid="9501",
)

scene_4 = Scene(
    id="S1A_IW_SLC__1SDV_20240109T195221_20240109T195248_052034_0649D6_1FF6",
    mission="S1A",
    beam_mode="IW",
    product_type="SLC",
    resolution_class="_",
    processing_level="1",
    product_class="S",
    polarisation="DV",
    start_date="20240109T195221",
    stop_date="20240109T195248",
    absolute_orbit_number="052034",
    mission_data_take="0649D6",
    product_uid="1FF6",
)

scenes = [scene_1, scene_2, scene_3, scene_4]


@pytest.mark.parametrize("scene", scenes)
def test_parse_scene_file_dates(scene: Scene):
    date_tuple = (scene.start_date_datetime, scene.stop_date_datetime)
    assert parse_scene_file_dates(scene.id) == date_tuple


@pytest.mark.parametrize("scene", scenes)
def test_parse_scene_file_sensor(scene: Scene):
    assert parse_scene_file_sensor(scene.id) == scene.mission


@pytest.mark.parametrize("scene", scenes)
def test_query_scene_from_asf(scene: Scene):
    query_result = query_scene_from_asf(scene.id)
    assert len(query_result) == 1


@pytest.mark.parametrize("scene", scenes)
def test_query_scene_from_cdse(scene: Scene):
    query_result = query_scene_from_cdse(scene.id)
    assert len(query_result) == 1


@pytest.mark.parametrize("scene", scenes)
def test_is_s1_id(scene: Scene):
    assert is_s1_id(scene.id)


@pytest.mark.parametrize("scene", scenes)
def test_is_s1_filename(scene: Scene):
    scene_filename = scene.id + ".SAFE"
    assert is_s1_filename(scene_filename)


@pytest.mark.parametrize("scene", scenes)
def test_extract_metadata_from_s1_id(scene: Scene):
    metadata_dict = extract_metadata_from_s1_id(scene.id)
    assert metadata_dict["mission"] == scene.mission
    assert metadata_dict["beam_mode"] == scene.beam_mode
    assert metadata_dict["product_type"] == scene.product_type
    assert metadata_dict["resolution_class"] == scene.resolution_class
    assert metadata_dict["processing_level"] == scene.processing_level
    assert metadata_dict["product_class"] == scene.product_class
    assert metadata_dict["polarisation"] == scene.polarisation
    assert metadata_dict["start_datetime"] == scene.start_date
    assert metadata_dict["stop_datetime"] == scene.stop_date
    assert metadata_dict["absolute_orbit_number"] == scene.absolute_orbit_number
    assert metadata_dict["mission_data_take"] == scene.mission_data_take
    assert metadata_dict["product_uid"] == scene.product_uid
