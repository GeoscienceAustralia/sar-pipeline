# sar-pyrosar-nci

This repository is designed to be used inside a specific project directory on the NCI, located at `/g/data/yp75/projects/pyrosar_processing/`

The `pyrosar_processing` folder already contains:

- a micromamba install with an environment called `pyrosar_rtc`
- folders for storing processed data
    - `data/gamma` for GAMMA processing
    - `data/snap` for SNAP processing
- folder for codebases (to review as reference)
    - `codebases/pyroSAR`
- a clone of the [`sar-pyrosar-nci` repository](https://github.com/GeoscienceAustralia/sar-pyrosar-nci)
- a clone of the [`s1-rtc-pyrosar-notebook` repository](https://github.com/abradley60/s1-rtc-pyrosar-notebook)
- symbolic links to shared objects required by GAMMA
    - `libfftw3f_GNU.so.3 -> /apps/gdal/3.6.4/lib64/libgdal.so.32`
    - `libgdal.so.20 -> /apps/fftw3/3.3.10/lib/libfftw3f_GNU.so.3`

## First time set up

### Add the project's micromamba to your environment variables
1. Add the following lines to your `$HOME/.bashrc` file:
```
# >>> mamba initialize >>>
# !! Contents within this block are managed by 'micromamba shell init' !!
export MAMBA_EXE='/g/data/yp75/projects/pyrosar_processing/.local/bin/micromamba';
export MAMBA_ROOT_PREFIX='/g/data/yp75/projects/pyrosar_processing/micromamba';
__mamba_setup="$("$MAMBA_EXE" shell hook --shell bash --root-prefix "$MAMBA_ROOT_PREFIX" 2> /dev/null)"
if [ $? -eq 0 ]; then
    eval "$__mamba_setup"
else
    alias micromamba="$MAMBA_EXE"  # Fallback on help from micromamba activate
fi
unset __mamba_setup
# <<< mamba initialize <<<
```
2. Source the file to apply the changes to the current session.
```
source .bashrc
```

This is only required once. After the first time, your `.bashrc` file will be run anytime you start a new session on NCI.

### Initialise pyroSAR's python API for GAMMA
If this is the first time you are using this repository, you must build `pyroSAR`'s Python API for GAMMA. This will be installed in your home directory on the NCI.

1. Activate the micromamba environment
```
micromamba activate pyrosar_rtc
```
2. Run the `initialise_gamma.py` script
```
python initialise_gamma.py
```
3. Check that you have the following in your home directory:
```
.pyrosar/
└── gammaparse
    ├── diff.py
    ├── disp.py 
    ├── __init__.py
    ├── isp.py
    ├── lat.py
    └── __pycache__
```