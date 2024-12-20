import os
import logging
import sys

logging.basicConfig(
    format="%(asctime)s | %(levelname)s : %(message)s",
    level=logging.INFO,
    stream=sys.stdout,
)
log = logging.getLogger("__file__")
log.setLevel(logging.INFO)

GAMMA_HOME_PATH = "/g/data/dg9/GAMMA/GAMMA_SOFTWARE-20230712"
REQUIRED_LIBS_PATH = "/g/data/yp75/projects/pyrosar_processing/sar-pyrosar-nci:/apps/fftw3/3.3.10/lib:/apps/gdal/3.6.4/lib64"

if os.environ.get("GAMMA_HOME", None) is None:
    
    print(f"Setting GAMMA to {GAMMA_HOME_PATH}")
    os.environ["GAMMA_HOME"] = GAMMA_HOME_PATH

else:
    print(os.environ.get("GAMMA_HOME"))


if os.environ.get("LD_LIBRARY_PATH", None) is None:
    print(f"Setting LD_LIBRARY_PATH to {REQUIRED_LIBS_PATH}")
    os.environ["LD_LIBRARY_PATH"] = REQUIRED_LIBS_PATH
else:
    print(os.environ.get("LD_LIBRARY_PATH"))

from pyroSAR.gamma.parser import autoparse