from sar_pipeline.aws.preparation.scenes import (
    query_scene_from_asf,
    query_scene_from_cdse,
)

import pytest


scene_1 = "S1A_EW_GRDM_1SDH_20200330T165825_20200330T165929_031907_03AF02_8570"
scene_2 = "S1B_EW_GRDM_1SDH_20210914T112333_20210914T112403_028693_036C96_3EA8"
scene_3 = "S1B_IW_SLC__1SSH_20211216T123605_20211216T123634_030050_03968D_9501"
scene_4 = "S1A_IW_SLC__1SDV_20240109T195221_20240109T195248_052034_0649D6_1FF6"

scenes = [scene_1, scene_2, scene_3, scene_4]


@pytest.mark.parametrize("scene", scenes)
def test_query_scene_from_asf(scene: str):
    query_result = query_scene_from_asf(scene)
    assert len(query_result) == 1


@pytest.mark.parametrize("scene", scenes)
def test_query_scene_from_cdse(scene: str):
    query_result = query_scene_from_cdse(scene)
    assert len(query_result) == 1
