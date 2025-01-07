from GAMMA_utils import set_gamma_env_variables

gamma_home_path = "/g/data/dg9/GAMMA/GAMMA_SOFTWARE-20230712"
ld_libraries_path = "/g/data/yp75/projects/pyrosar_processing/sar-pyrosar-nci:/apps/fftw3/3.3.10/lib:/apps/gdal/3.6.4/lib64"

set_gamma_env_variables(gamma_home_path, ld_libraries_path)