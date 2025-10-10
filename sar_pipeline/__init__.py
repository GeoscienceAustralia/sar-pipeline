from sar_pipeline._version import __version__
from pathlib import Path
import asf_search

asf_search.constants.INTERNAL.CMR_TIMEOUT = 90
PROJECT_ROOT_PATH = Path(__file__).parent.parent.resolve()
