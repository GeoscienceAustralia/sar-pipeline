# pyroSAR + GAMMA
> **_NOTE:_**  This is a work in progress and has not been finalised.

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