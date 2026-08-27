# AWS PyroSAR-GAMMA Workflow

- [AWS pyroSAR + GAMMA Pipeline (Sentinel-1 IW/EW NRB)](#aws-pyrosar-gamma-pipeline-sentinel-1-iw-ew-nrb)
  - [1. About](#1-about)
    - [1.1. Requirements](#11-requirements)
  - [2. Example products](#2-example-products)
  - [3. Running the pipeline](#3-running-the-pipeline)
    - [3.1. Overview](#31-overview)
    - [3.2. Environment variables](#32-environment-variables)
    - [3.3. Pipeline arguments and configuration](#33-pipeline-arguments-and-configuration)
    - [3.4. Running multiple jobs in parallel](#34-running-multiple-jobs-in-parallel)
  - [4. Project setup](#4-project-setup)
    - [4.1. Development setup](#41-development-setup)
    - [4.2. Gamma software](#42-gamma-software)
    - [4.3. Running sar-pipeline in Docker image](#43-running-sar-pipeline-in-docker-image)
    - [4.4. Running sar-pipeline locally](#44-running-sar-pipeline-locally)
    - [4.5. Standalone GAMMA software](#45-standalone-gamma-software)


## 1. About

The pyrosar_gamma pipeline can be used to create Sentinel-1 Normalised Radar Backscatter (NRB) data captured in the both IW and EW modes (in Single Look Complex format).

The dependant codebases managed by GA used in the pipeline are:
- [dem-handler](https://github.com/GeoscienceAustralia/dem-handler)
- [sar-pipeline](https://github.com/GeoscienceAustralia/sar-pipeline/tree/main/sar_pipeline)

The primary output from the pyrosar_gamma pipeline is Normalised Radar Backscatter, including ancillary layers (e.g. local incidence angle).
There are no static layers, and outputs are provided at the level of a scene, rather than bursts.

### 1.1. Requirements

You will need an AWS EC2 instance to run the code in. (TODO add specs!)

## 2. Example products

The following is an example of NRB outputs for a given acquisition.
The primary analysis ready NRB data product are the `HH_slc_mli_gamma0-rtc_geo.tif`, for linear, and `HH_slc_mli_gamma0-rtc_geo_db.tif` for log scale gamma0 backscatter.

```text
S1A__EW___A_20250419T221041_commands.sh
S1A__EW___A_20250419T221041_dem_seg_geo.tif
S1A__EW___A_20250419T221041_HH_grd_mli_gamma0-rtc_geo.tif
S1A__EW___A_20250419T221041_HH_grd_mli_gamma0-rtc_geo_db.tif
S1A__EW___A_20250419T221041_inc_geo.tif
S1A__EW___A_20250419T221041_ls_map_geo.tif
S1A__EW___A_20250419T221041_manifest.safe
S1A__EW___A_20250419T221041_pix_area_gamma0_geo.tif
S1A__EW___A_20250419T221041_pix_ratio_geo.tif
```

## 3. Running the pipeline

### 3.1. Overview

The pipeline has been set up to run via command line interface (CLI) calls on the AWS EC2 instance.
**NOTE**: The CLI is available if you have activated a Pixi environment that has sar-pipeline installed.
The CLI functions can be found in the pyrosar_gamma [cli.py](../../sar_pipeline/pipelines/pyrosar_gamma/aws/cli.py).

### 3.2. Environment variables

At runtime, the pipeline expects the following environment variables to be set.
These can be passed in using an environment file (`.env`).

Credentials for the Aus Cop Hub were provided internally.
The Aus Cop Hub can be contacted at CopernicusAustralasia@ga.gov.au or via the [website](https://www.copernicus.gov.au/).

[.env.example](../../.env.example)

```
# Variables used on all platforms
EARTHDATA_LOGIN=
EARTHDATA_PASSWORD=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
CDSE_LOGIN=
CDSE_PASSWORD=
AUS_COP_HUB_LOGIN=
AUS_COP_HUB_PASSWORD=
AUS_COP_HUB_CLIENT_ID=
AUS_COP_HUB_CLIENT_SECRET=
PYGSSEARCH_CONDA_ENV=
```

### 3.3. Pipeline arguments and configuration

After activating the required Pixi environment and at runtime, the [pyrosar-gamma-rtc-run-workflow](../../sar_pipeline/pipelines/pyrosar_gamma/aws/cli.py) CLI is run, with the following usage:

```bash
../../sar_pipeline/pipelines/pyrosar_gamma/aws/cli.py  --scene SCENE [OPTIONS]
```
where `SCENE` is an individual scene ID.

This command will by default create and use `sar-processing` directory inside the project root. The intermediate files will be downloaded to `sar-processing/downloads` and the outputs will go into `sar-processing/r1_rtc` folder. These paths could be controlled via `--download-folder` and `--out-folder` arguments.

The CLI has the following options:

```bash
--scene TEXT # required
--dem-type TEXT
--download-folder DIRECTORY
--out-folder DIRECTORY
--scene-data-source TEXT
--orbit-data-source TEXT
--gamma-library DIRECTORY
--gamma-env TEXT
--geocode-spacing INTEGER
--geocode-scaling [linear|db|both]
--etad DIRECTORY
--make-folders
--dotenv-location TEXT
--target-crs [4326|3031]
--help
```

* `scene` -> scene id. E.g S1A_IW_SLC__1SSH_20220101T124744_20220101T124814_041267_04E7A2_1DAD".
* `dem-type` -> The type of DEM that should be downloaded for processing the scene. If 'best' is provided, logic will be used to select the most appropriate DEM. One of `best`, `cop_glo30`, `REMA_32`, `REMA_10`, `REMA_2`.
* `download-folder` -> Path to the folder where downloaded files should go.
* `out-folder` -> Path to the folder where final products will be written.
* `scene-data-source` -> Where to download the scene from. Can be passed as a string or list of preferences separated by a space. If the scene cannot be found at the first preference, the next will be used. One or a space separated list of `AUS_COP_HUB`, `CDSE`, `ASF`.
* `orbit-data-source` -> Where to download the orbit files from. Can be passed as a string or list of preferences separated by a space. If the orbits files cannot be found at the first preference, the next will be used. One or a space separated list of `AUS_COP_HUB`, `CDSE`, `ASF`.
* `gamma-library` -> Path to the gamma library for processing.
* `gamma-env` -> Name of the gamma environment for processing. This should be set up with the gamma library specified by --gamma-library. By default set to "<Project_root>/.pixi/envs/default/lib:$HOME/gamma_symlinks" .
* `geocode-spacing` -> The geocoding grid spacing in meters. Default is 20m..
* `geocode-scaling` -> The scaling convention for the geocoded output. Default is 'both', which rescales the values using linear and decibel scaling; one of `linear`, `db` or `both`.
* `etad` -> Path to the ETAD file to use for processing."
"If not provided, the workflow will attempt to download an ETAD file from the CDSE for the scene date. If no ETAD file can be found, processing will continue without an ETAD file.
* `make-folders` -> Create folders.
* `dotenv-location` -> Location of the environment file (.env). Assumed to be the project root directory if not provided.
* `target-crs` -> The EPSG number for the target coordinate reference system. Only `4326` and `3031` are supported.
* `help` -> Show the CLI help message.

### 3.4. Running multiple jobs in parallel

Running the multiple jobs (scenes) in parallel requires a docker image to run each scene in its own container. Refer to section [4.3](#43-running-sar-pipeline-in-docker-image) for more information about building and running the docker container. To run the multiple jobs use the command below after entering the root of the project:

```bash
pyrosar-gamma-run-parallel-jobs --scenes-csv
```

`scenes-csv` is the path to a csv file that must be provided to the command. It contains the name(ID) of each scene as its rows and the command will run one container per each row. The image name to be used in the containers is `sar-pipeline-pyrosar-gamma:latest` by default. The commands tries to find the image locally, otherwise tries to build it from the Dockerfile that must be present at the root of the project inside `Docker/pyrosar_gamma` directory. If the Dockerfile is not present, the command will fail. You can pass a different image name using `--image-name` argument if required.

By default, the command runs the jobs in batches of 10 containers. You can change this bys setting the number using `--max-workers` argument.

**NOTE** Make sure your AWS credentials are properly exported to the `.env` file required for the job inside the root pf the project directory.

## 4. Project setup
Clone the repository to a project folder that you own, where you have read, write and execution permissions.

### 4.1. Development setup
The project uses Pixi to install the required environment locally for implementing and testing the code. You need to first install Pixi on your system following the link:
[Pixi installation](https://pixi.prefix.dev/latest/installation/)

After installing pixi run `pixi install --all` to install both default and dev environments. You can activate each environment by running `pixi shell -e <env name>`

### 4.2 GAMMA software

You need to have GAMMA software locally present in you system. The preferred location for the software is `/usr/local/GAMMA_SOFTWARE-20230712`.

Copy the GAMMA software's files to `/usr/local/GAMMA_SOFTWARE-20230712` if you haven't already. You might need to give execution permission access to the folder. Run `chmod -R a+x /usr/local/GAMMA_SOFTWARE-20230712`

### 4.3. Running sar-pipeline in Docker image

The workflow could be run using a docker image. The docker file can be found at [Docker/pyrosar_gamma/Dockerfile](../../Docker/pyrosar_gamma/Dockerfile).
You can build the docker image via the command:

```bash
docker build -t sar-pipeline-pyrosar-gamma -f Docker/pyrosar_gamma/Dockerfile .
```

The docker image could be run via the pixi command:
```bash
pyrosar-gamma-rtc-run-docker-container --scene SCENE
```

This will assume that you have a `.env` file present in the root folder of your project and GAMMA software is locate locally at `/usr/local/GAMMA_SOFTWARE-20230712`
Again running the image will download and generate files in the default folders as explained in [3.3](#33-pipeline-arguments-and-configuration).

Alternatively you can run the image via `docker run` command and pass the desired arguments to the entry point.

### 4.4. Running sar-pipeline locally

1. Install the dependencies required to run the software

```bash
sudo apt update
sudo apt-get install libsqlite3-dev libzstd-dev libwebp-dev libjson-c-dev libgtk-3-0
```

2. Create a symlink to the required library by GAMMA software.
The version of GAMMA currently used by the pipeline (20230712) requires a symlink for `libgdal.so.20`, as this lib file is not available in the Pixi environment.
The following steps are used to create the symlink:

  * Create a directory for symlinks
```bash
mkdir ~/gamma_symlinks
```
  * Identify the location of gdal library files in your Conda environment
```bash
cd $PROJECT_ROOT/.pixi/envs/default/lib
find . -name "libgdal*"
```
Where `$PROJECT_ROOT` is the absolute path to the root directory of your project.
  * Confirm that `./libgdal.so.38` appears in the list. version number `38` could change depending on the version of GDAL installed, therefore you might see a different number.
  * Create the symlink
```bash
cd ~/gamma_symlinks
ln -s $PROJECT_ROOT/.pixi/envs/default/lib/libgdal.so.38 libgdal.so.20
```
If you don't have your project root directory in an environment variable, you need to use the absolute path of it instead.

Pixi will install GDAL inside its environment. The symlink you created before should point GAMMA to the right libraries [Development setup](#43-development-setup)

3. Set the correct environment variables either in your `~/.bashrc` file or at runtime. If setting in `~/.bashrc` you might need to run `source ~/.bashrc` to activate the new variables.
```bash
export GAMMA_HOME="/usr/local/GAMMA_SOFTWARE-20230712"
export LD_LIBRARY_PATH="$PROJECT_ROOT/.pixi/envs/default/lib:$HOME/gamma_symlinks"
```

4. The pyroSAR library is a python wrapper for various GAMMA command line utilities.
As such, it needs to read the GAMMA commands and create the appropriate Python wrapper functions before first use.
You can check whether it exists by seeing if you have a folder at `~/.pyrosar/gammaparse`.
If the files do not exist, they will be automatically generated when you run the pipeline. If they exist, the automatic generation will be skipped.
If the files are not generated at runtime, the most likely underlying reasons fo the issue are:
  * The prerequisites are not installed properly (step 2).
  * The symlink is not created correctly.
  * The environment variables are not set correctly


**Note** It is not required but you can also pre-generate the pyroSAR python bindings by running the script below:

  1. Activate the sar-pipeline conda environment
```bash
pixi shell
```
  2. Set the `PROJECT_ROOT` environment variable via an `export` command.
  3. Run a new Python REPL
```bash
python
```
  4. Specify the required paths, set these as environment variables, then run the GAMMA `autoparse` function from pyroSAR:
```python
>>> gamma_lib_dir = "/usr/local/GAMMA_SOFTWARE-20230712"
>>> gamma_env_var = f"{os.environ["PROJECT_ROOT"]}/.pixi/envs/default/lib:{os.environ["HOME"]}/gamma_symlinks"
>>> from sar_pipeline.utils.gamma import set_gamma_env_variables
>>> set_gamma_env_variables(gamma_lib_dir, gamma_env_var)
>>> from pyroSAR.gamma.parser import autoparse
>>> exit()
```
  5. Check that the following files are available in your NCI home directory at `~/.pyrosar/gammaparse`:
```bash
diff.py
disp.py
__init__.py
isp.py
lat.py
msp.py
__pycache__
```

### 4.5. Standalone GAMMA software
**Note**: <I>**This is not required for running `sar-pipeline`.**</I> This is just to install the software and use it via its own commands and python bindings if required. `sar-pipeline` uses different libraries for the GAMMA software's python bindings which is explained in previous sections.

If you wanted to run GAMMA software as an standalone tool and not via the `sar-pipeline` package, you should follow the GAMMA software's installation documentation and as part of it install GDAL and PROJ. In some cases installing GDAL and PROJ from package manager will not install the right version and there will be missing libraries. If you are getting GDAL or PROJ related errors, you will need to build the packages from source then.

In section 4 of the `INSTALL_linux.html` file from GAMMA software's documentation, the Follow PROJ gamma GDAL installation under `CentOS/RHEL 7` to build from source. Build PROJ first and When gdal zip file is downloaded and unzipped go to the unzipped folder and do this first:

Add `#include <limits>` to the top of `gdal-2.4.2/ogr/ogrsf_frmts/cad/libopencad/dwg/r2000.cpp` file and then build GDAL.

If you have followed the installation guide correctly (specially when setting the environment variables) GAMMA commands such as `disras` should work.

