from spatialist.ancillary import finder
import re
import subprocess as sp
import os

GAMMA_HOME_ENV = "GAMMA_HOME"
LD_LIBRARY_ENV = "LD_LIBRARY_PATH"


def set_gamma_env_variables(gamma_home_path: str, ld_libraries_path: str):
    """Sets the required GAMMA environment variables: GAMMA_HOME and LD_LIBRARY_PATH

    Parameters
    ----------
    gamma_home_path : str
        The path to the GAMMA binary files, to be assigned to GAMMA_HOME
    ld_libraries_path : str
        The path to sym-links required to support running GAMMA, to be assigned to LD_LIBRARY_PATH
    """
    gamma_env = os.environ.get(GAMMA_HOME_ENV, None)
    ld_lib_env = os.environ.get(LD_LIBRARY_ENV, None)

    if gamma_env is None:
        os.environ[GAMMA_HOME_ENV] = gamma_home_path
    if ld_lib_env is None:
        os.environ[LD_LIBRARY_ENV] = ld_libraries_path
    else:
        os.environ[LD_LIBRARY_ENV] = os.path.join(ld_libraries_path, ":", ld_lib_env)


def check_gamma_modules(
    gamma_home_path: str,
    ld_libraries_path: str,
    commands_to_skip: list[str] = [
        "coord_trans",
        "phase_sum",
        "dishgt",
        "SLC_cat",
        "ras_ratio_dB",
        "ptarg",
    ],
):
    """Iterates through GAMMA modules and checks that each binary can be run with the supplied environment variables.

    Parameters
    ----------
    gamma_home_path : str
        The path to the GAMMA binary files, to be assigned to GAMMA_HOME
    ld_libraries_path : str
        The path to sym-links required to support running GAMMA, to be assigned to LD_LIBRARY_PATH
    commands_to_skip : list[str], optional
        Any GAMMA commands to skip, which may have more complex requirements.
        By default [ "coord_trans", "phase_sum", "dishgt", "SLC_cat", "ras_ratio_dB", "ptarg", ]
    """

    set_gamma_env_variables(gamma_home_path, ld_libraries_path)

    for module in finder(gamma_home_path, ["[A-Z]*"], foldermode=2):
        print(module)
        for submodule in ["bin", "scripts"]:
            print(f"{module}/{submodule}")
            for cmd in sorted(
                finder(module + "/" + submodule, [r"^\w+$"], regex=True),
                key=lambda s: s.lower(),
            ):
                command_base = os.path.basename(cmd)
                if command_base in commands_to_skip:
                    print("    skipping " + command_base)
                else:
                    print("  " + command_base)
                    proc = sp.Popen(
                        cmd,
                        stdin=sp.PIPE,
                        stdout=sp.PIPE,
                        stderr=sp.PIPE,
                        universal_newlines=True,
                    )
                    out, err = proc.communicate()
                    out += err
                    usage = re.search("usage:.*(?=\n)", out)
                    if usage is None:
                        print("    " + err)
            print("\n\n")
