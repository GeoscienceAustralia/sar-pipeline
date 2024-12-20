from spatialist.ancillary import finder
import re
import subprocess as sp
import os

GAMMA_HOME_PATH = "/g/data/dg9/GAMMA/GAMMA_SOFTWARE-20230712"
REQUIRED_LIBS_PATH = "/g/data/yp75/projects/pyrosar_processing/sar-pyrosar-nci"

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

commands_to_skip = ["coord_trans", "phase_sum", "dishgt", "SLC_cat", "ras_ratio_dB", "ptarg"]

for module in finder(GAMMA_HOME_PATH, ['[A-Z]*'], foldermode=2):
    print(module)
    for submodule in ['bin', 'scripts']:
        print(f"{module}/{submodule}")
        for cmd in sorted(finder(module+"/"+submodule, [r'^\w+$'], regex=True), key=lambda s: s.lower()):
            command_base = os.path.basename(cmd)
            if command_base in commands_to_skip:
                print("    skipping " + command_base)
            else:
                
                print("  " + command_base)
                proc = sp.Popen(cmd, stdin=sp.PIPE, stdout=sp.PIPE, stderr=sp.PIPE, universal_newlines=True)
                out, err = proc.communicate()
                out += err
                usage = re.search('usage:.*(?=\n)', out)
                if usage is None:
                    print("    " + err)
        print("\n\n")