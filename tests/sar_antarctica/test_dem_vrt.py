from sar_pipeline.nci.preparation.create_dem_vrt import (
    find_tiles,
    build_vrt,
    build_tileindex,
)

from pathlib import Path
import os

CURRENT_DIR = Path(__file__).parent.resolve()
TEST_DATA_PATH = CURRENT_DIR / Path("data/copernicus_30m_world")

EXPECTED_DATA_FILES = [
    TEST_DATA_PATH
    / "Copernicus_DSM_COG_10_S80_00_E178_00_DEM/Copernicus_DSM_COG_10_S80_00_E178_00_DEM.tif",
    TEST_DATA_PATH
    / "Copernicus_DSM_COG_10_S80_00_E179_00_DEM/Copernicus_DSM_COG_10_S80_00_E179_00_DEM.tif",
    TEST_DATA_PATH
    / "Copernicus_DSM_COG_10_S80_00_W180_00_DEM/Copernicus_DSM_COG_10_S80_00_W180_00_DEM.tif",
]
EXPECTED_VRT_FILE = TEST_DATA_PATH / "copdem_test.vrt"

TEST_FILE_LIST_PATH = Path("temp.txt")
TEST_VRT_PATH = TEST_DATA_PATH / "temp.vrt"
TEST_TINDEX_PATH = TEST_DATA_PATH / "temp.gpkg"


tiles = find_tiles(TEST_DATA_PATH, "Copernicus_DSM_COG_10_S80_00_????_00_DEM.tif")
list_tiles = list(tiles)


def test_find_tiles_for_vrt():
    assert set(list_tiles) == set(EXPECTED_DATA_FILES)


def test_build_vrt():
    build_vrt(list_tiles, TEST_VRT_PATH, run=False)
    assert TEST_FILE_LIST_PATH.exists

    with open(TEST_FILE_LIST_PATH, "r") as f:
        lines = [Path(line.rstrip()) for line in f.readlines()]
    assert lines == list_tiles

    build_vrt(list_tiles, TEST_VRT_PATH, run=True)
    assert TEST_VRT_PATH.exists

    os.remove(TEST_VRT_PATH)


def test_build_tindex():
    build_tileindex(list_tiles, TEST_TINDEX_PATH, run=False)
    assert TEST_FILE_LIST_PATH.exists

    with open(TEST_FILE_LIST_PATH, "r") as f:
        lines = [Path(line.rstrip()) for line in f.readlines()]
    assert lines == list_tiles

    build_tileindex(list_tiles, TEST_TINDEX_PATH, run=True)
    assert TEST_TINDEX_PATH.exists

    os.remove(TEST_TINDEX_PATH)
