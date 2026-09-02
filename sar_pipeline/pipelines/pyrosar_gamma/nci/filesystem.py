from pathlib import Path
import logging

from dem_handler.dem.cop_glo30 import get_cop30_dem_for_bounds

logging.basicConfig(level=logging.INFO)


def get_dem_nci(
    scene: Path,
    scene_bounds: tuple[float, float, float, float],
    output_dir: Path,
    nci_dem_dir: Path = Path(
        "/g/data/v10/eoancillarydata-2/elevation/copernicus_30m_world/"
    ),
    nci_geoid: Path = Path(
        "/g/data/yp75/projects/ancillary/geoid/us_nga_egm2008_1_4326__agisoft.tif"
    ),
) -> Path:
    if not output_dir.exists():
        output_dir.mkdir(parents=True, exist_ok=True)
    dem_file = output_dir / f"{scene.stem}.tif"

    if not dem_file.exists():
        _, _, _ = get_cop30_dem_for_bounds(
            scene_bounds,
            dem_file,
            ellipsoid_heights=True,
            adjust_at_high_lat=True,
            buffer_pixels=10,
            cop30_folder_path=nci_dem_dir,
            geoid_tif_path=nci_geoid,
        )

    return dem_file
