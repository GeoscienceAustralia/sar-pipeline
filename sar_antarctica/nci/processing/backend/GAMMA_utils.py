import os

GAMMA_HOME_ENV = "GAMMA_HOME"
LD_LIBRARY_ENV = "LD_LIBRARY_PATH"

def set_gamma_env_variables(gamma_home_path: str, ld_libraries_path: str):
    gamma_env = os.environ.get(GAMMA_HOME_ENV, None)
    ld_lib_env = os.environ.get(LD_LIBRARY_ENV, None)

    if gamma_env is None:
        os.environ[GAMMA_HOME_ENV] = gamma_home_path

    if ld_lib_env is None:
        os.environ[LD_LIBRARY_ENV] = ld_libraries_path
    else:
        os.environ[LD_LIBRARY_ENV] = os.path.join(ld_libraries_path, ":", ld_lib_env)