import os
from pathlib import Path
from typing import Generator

def find_tiles(source_dir: Path, pattern: str) -> Generator[Path, None, None]:
    """_summary_

    Parameters
    ----------
    source_dir : Path
        The directory to search for files
    pattern : str
        The pattern to search for
        e.g. DEM_folder/*.tif

    Returns
    -------
    Generator[Path, None, None]
        A generator that yeilds `Path` objects for all files matching the pattern
        e.g. /path/to/DEM_folder/DEM_file.tif
    """

    tiles = source_dir.rglob(pattern)

    return tiles


def build_vrt(
    tiles: Generator[Path, None, None] | list[Path],
    vrt_path: str | os.PathLike,
    run: bool = True,
):
    """Generic function for building a VRT from a generator of tile paths

    Parameters
    ----------
    tiles : Generator[Path, None, None] | list[Path]
        A generator (or list) that provides `Path` objects for tiles
        e.g. /path/to/DEM_folder/DEM_file.tif
    vrt_path : str | os.PathLike
        Where to write the VRT to, ending in .vrt
    run : bool, optional
        Whether to run the step to create the VRT, by default True
        Can use False to generate the temporary file and check
    """
    with open("temp.txt", "w") as f:
        f.writelines(f"{tile}\n" for tile in tiles)

    if run:
        os.system(f"gdalbuildvrt -input_file_list temp.txt {vrt_path}")

        os.remove("temp.txt")


def build_tileindex(
    tiles: Generator[Path, None, None] | list[Path],
    tindex_path: str | os.PathLike,
    run: bool = True,
):
    """Generic function for building a tile index from a generator of tile paths

    Parameters
    ----------
    tiles : Generator[Path, None, None]
        A generator (or list) that provides `Path` objects for tiles
        e.g. /path/to/DEM_folder/DEM_file.tif
    vrt_path : str | os.PathLike
        Where to write the tile index to, ending in .gpkg
    run : bool, optional
        Whether to run the step to create the tile index, by default True
        Can use False to generate the temporary file and check
    """
    with open("temp.txt", "w") as f:
        f.writelines(f"{tile}\n" for tile in tiles)

    if run:
        os.system(f"gdaltindex {tindex_path} --optfile temp.txt")

        os.remove("temp.txt")


def create_glo30_dem_south_vrt():
    """Create a VRT for the Copernicus Global 30m DEM on NCI"""

    SOURCE_DIR = Path("/g/data/v10/eoancillarydata-2/elevation/copernicus_30m_world")
    PATTERN = "Copernicus_DSM_COG_10_S??_00_????_00_DEM/*.tif"
    VRT_PATH = Path("/g/data/yp75/projects/ancillary/dem/copdem_south.vrt")

    tiles = find_tiles(SOURCE_DIR, PATTERN)

    build_vrt(tiles, VRT_PATH)
