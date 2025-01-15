import os
from pathlib import Path

def build_vrt(source_dir: Path, pattern: str, vrt_path: str | os.PathLike):
    """Generic function for building a VRT from files matching a given pattern in a source directory

    Parameters
    ----------
    source_dir : Path
        The directory to search for files
    pattern : str
        The pattern to search for
        e.g. Copernicus_DSM_COG_10_S??_00_????_00_DEM/*.tif
    vrt_path : str | os.PathLike
        Where to write the VRT to
    """

    tiles = source_dir.rglob(pattern)

    with open("vrt_temp.txt", "w") as f:
        f.writelines(f"{tile}\n" for tile in tiles)

    os.system(f'gdalbuildvrt -input_file_list vrt_temp.txt {vrt_path}')

    os.remove("vrt_temp.txt")

def create_glo30_dem_south_vrt():
    """Create a VRT for the Copernicus Global 30m DEM on NCI
    """
    
    SOURCE_DIR = Path("/g/data/v10/eoancillarydata-2/elevation/copernicus_30m_world")
    PATTERN = "Copernicus_DSM_COG_10_S??_00_????_00_DEM/*.tif"
    VRT_PATH = Path("/g/data/yp75/projects/ancillary/dem/copdem_south.vrt")

    build_vrt(SOURCE_DIR, PATTERN, VRT_PATH)