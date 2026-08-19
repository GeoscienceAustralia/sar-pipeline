from sar_pipeline._version import __version__
from sar_pipeline.utils.stac import S3StacIO
from pystac import StacIO
from pathlib import Path
import asf_search

asf_search.constants.INTERNAL.CMR_TIMEOUT = 90
PROJECT_ROOT_PATH = Path(__file__).parent.parent.resolve()
StacIO.set_default(S3StacIO)
