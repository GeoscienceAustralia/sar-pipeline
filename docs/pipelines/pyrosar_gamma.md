# pyroSAR + GAMMA
> **_NOTE:_**  This is a work in progress and has not been finalised.

### Finding the location of a scene on the NCI
The `find-scene` command will display the location of a given scene on the NCI.
The full path to the scene is required as the input to other commands.

Example usage:
```
$ find-scene S1A_EW_GRDM_1SDH_20240129T091735_20240129T091828_052319_065379_0F1E

/path/to/scene/S1A_EW_GRDM_1SDH_20240129T091735_20240129T091828_052319_065379_0F1E.zip
```

### Submit a workflow
This will submit a job request to the NCI based on the job parameters and file paths in the supplied config. 
The [default config](../../sar_pipeline/nci/configs/default.toml) will be used if no other config is provided.

Example usage
```
$ submit-pyrosar-gamma-workflow /path/to/scene/S1A_EW_GRDM_1SDH_20240129T091735_20240129T091828_052319_065379_0F1E.zip
```
This will submit a job to the NCI with the default config.
To use a different config, run the command and supply the `--config` option
```
--config /path/to/config.toml
```

### Run a workflow interactively
If you are still testing a workflow, it is best to run it in an interactive session.
While in an interactive session, you can run the workflow directly. 

Example usage
```
$ run-pyrosar-gamma-workflow /path/to/scene/S1A_EW_GRDM_1SDH_20240129T091735_20240129T091828_052319_065379_0F1E.zip
```
To use a different config, run the command and supply the `--config` option
```
--config /path/to/config.toml
```

## GAMMA

Ensure there are symbolic links in the source code directory:

Load required shared objects for GAMMA binaries by running
```
module load gdal
module load fftw3
```

Move to project directory
`cd <path/to/source/code>`

Create symlinks in project directory by running
```
ln -s /apps/gdal/3.6.4/lib64/libgdal.so.32 libgdal.so.20
ln -s /apps/fftw3/3.3.10/lib/libfftw3f_GNU.so.3
```

Activate the python env by running 
```
micromamba activate sar-pipleine
```

Run the one-time script to create pyroSAR's python api using 
```
python initialise_gamma.py
```

Check that you have the following in your home directory:
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