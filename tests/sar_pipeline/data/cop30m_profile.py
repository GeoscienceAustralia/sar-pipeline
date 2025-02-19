import numpy as np
from affine import Affine
from rasterio.crs import CRS

TEST_COP30_PROFILE_1 = (
    (140, -66, 141, -65),
    {
        'driver': 'GTiff', 
        'dtype': 'float32', 
        'nodata': np.nan, 
        'height': 3600, 
        'width': 1800, 
        'count': 1, 
        'crs': CRS.from_epsg(4326), 
        'transform': Affine(0.0005555555555555556, 0.0, 140.0,0.0, -0.0002777777777777778, -65.0), 
        'blockysize': 1, 
        'tiled': False, 
        'interleave': 'band'
    }
)

TEST_COP30_PROFILE_2 = (
    (0, -90, 1, -86),
    {
        'driver': 'GTiff', 
        'dtype': 'float32', 
        'nodata': np.nan, 
        'height': 14400, 
        'width': 360, 
        'count': 1, 
        'crs': CRS.from_epsg(4326), 
        'transform': Affine(0.002777777777777778, 0.0, 0.0, 0.0, -0.0002777777777777778, -86.0), 
        'blockysize': 1, 
        'tiled': False, 
        'interleave': 'band'
    }
)

       