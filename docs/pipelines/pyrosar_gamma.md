# NCI pyroSAR + GAMMA Pipeline (Sentinel-1 EW NRB)
> **_NOTE:_**  This is a work in progress and has not been finalised.

## 1. About

The pyrosar_gamma pipeline can be used to create Sentinel-1 Normalised Radar Backscatter (NRB) data captured in the EW mode (in Ground Range Detected format).

The dependant codebases managed by GA used in the pipeline are:
- [dem-handler](https://github.com/GeoscienceAustralia/dem-handler)
- [sar-pipeline](https://github.com/GeoscienceAustralia/sar-pipeline/tree/main/sar_pipeline)

The primary output from the pyrosar_gamma pipeline is Normalised Radar Backscatter, including ancillary layers (e.g. local incidence angle). 
There are no static layers, and outputs are provided at the level of a scene, rather than bursts.

### 1.1. Requirements

You will need an NCI account as well as membership for the following projects:
* `dg9` - For access to GAMMA software
* `fj7` - For access to Copernicus Australasian Datahub data holdings

You will additionally need memberships for a relevant filesystem and compute resource.
For Digital Earth Antarctica, the filesystem is under project `yp75` and compute is allocated to `u46`.

## 2. Example products

The following is an example of NRB outputs for a given acquisition.
The primary analysis ready NRB data product is the `HH_grd_mli_gamma0-rtc_geo_4326.tif`, which contains linear gamma0 backscatter.

```text
S1A__EW___A_20250419T221041_commands.sh
S1A__EW___A_20250419T221041_dem_seg_geo_4326.tif
S1A__EW___A_20250419T221041_HH_grd_mli_gamma0-rtc_geo_4326.tif
S1A__EW___A_20250419T221041_inc_geo_4326.tif
S1A__EW___A_20250419T221041_ls_map_geo_4326.tif
S1A__EW___A_20250419T221041_manifest.safe
S1A__EW___A_20250419T221041_pix_area_gamma0_geo_4326.tif
S1A__EW___A_20250419T221041_pix_ratio_geo_4326.tif
```

## 3. Running the pipeline

### 3.1. Overview

The pipeline has been set up to run via command line interface (CLI) calls on the NCI.
The CLI is available if you have activated a Conda environment that has sar-pipeline installed. 
The CLI functions can be found in the pyrosar_gamma [cli.py](../../sar_pipeline/pipelines/pyrosar_gamma/cli.py).

The login node of the NCI has very limited internet access, so the pipeline is designed to access Sentinel-1 files directly from the NCI. 
The main approach uses the Copernicus Australasian Datahub (Aus Cop Hub) API to search for a scene's UUID, which is then converted to an NCI path. 
If this fails, the pipeline will fall back to searching the older (and no longer updated) filesystem.
This back-up can be useful in the case of accessing scenes captured prior to mid-2025 if they're not available through the Aus Cop Hub API.

### 3.2. Environment variables

At runtime, the pipeline expects the following environment variables to be set.
These can be passed in using an environment file (`.env`).

Credentials for the Aus Cop Hub were provided internally.
The Aus Cop Hub can be contacted at CopernicusAustralasia@ga.gov.au or via the [website](https://www.copernicus.gov.au/).

[.env.example](../../.env.example)

```
# Variables used on all platforms
AUS_COP_HUB_LOGIN=
AUS_COP_HUB_PASSWORD=
AUS_COP_HUB_CLIENT_ID=
AUS_COP_HUB_CLIENT_SECRET=
PYGSSEARCH_CONDA_ENV=

# Variables used on NCI only
CONDA_EXE=
NCI_API_FILE_LOCATION=
NCI_FILESYSTEM_FILE_LOCATION=
```

The NCI variables have the following uses:
* `CONDA_EXE`: the path to the Conda executable that has environments for sar-pipeline and pygssearch-env.
Should be of the form `/path/to/conda/install/bin/conda`
* `NCI_API_FILE_LOCATION`: the path to the filesystem containing the Aus Cop Hub data holdings for either Australia or Antarctica.
* `NCI_FILESYSTEM_FILE_LOCATION`: the path to the (now non-updated) filesystem containing the original Aus Cop Hub data holdings, prior to the development and implementation of the API. 

For questions about the location of files on the NCI filesystem, contact the Aus Cop Hub team at CopernicusAustralasia@ga.gov.au or via the [website](https://www.copernicus.gov.au/).

### 3.3. Pipeline arguments and configuration

At runtime, the [submit-pyrosar-gamma-workflow](../../sar_pipeline/pipelines/pyrosar_gamma/cli.py) CLI is run, with the following usage:

```bash
submit-pyrosar-gamma-workflow [OPTIONS] SCENE
```
where `SCENE` is an individual scene ID, path to a scene as a .zip file, or path to a list of scene IDs/paths contained in a single .txt file`. 

The CLI has the following options:

```bash
-c, --config FILE
--spacing INTEGER # required
--scaling [linear|db|both] # required
--target-crs [4326|3031] # required
--orbit-dir DIRECTORY # required
--orbit-type [POE|RES|either] # required
--etad-dir DIRECTORY
--output-dir DIRECTORY
--gamma-lib-dir DIRECTORY
--gamma-env-var TEXT
--ncpu TEXT
--mem TEXT
--queue TEXT
--project TEXT
--walltime TEXT
--dry-run
--dotenv-location DIRECTORY
--help
```

* `config` -> A .toml file that specifies values for all the above options, which will be used by default if no other value is provided.
* `spacing` -> The target resolution for the output product, typically 40 for EW.
* `scaling` -> The value scaling of the backscatter values; one of `linear`, `db` or `both`.
* `target-crs` -> The EPSG number for the target coordinate reference system. Only 4326 and 3031 are supported.
* `orbit-dir` -> Path to where orbit files are stored on NCI.
* `orbit-type` -> The orbit type to use, one of `POE` for precise, `RES` for restitutional, or `either` for the most recent.
* `etad-dir` -> Path to where ETAD correction files are stored. If provided, the ETAD correction will be applied.
* `output-dir` -> Path to where outputs will be stored.
* `gamma-lib-dir` -> Path to GAMMA software binaries.
* `gamma-env-var` -> Environment variable to point to symlinked .so objects to ensure GAMMA runs.
* `ncpu` -> Number of CPU to request.
* `mem` -> Amount of memory to request in GB.
* `queue` -> NCI queue to submit to.
* `project` -> NCI project to submit to.
* `walltime` -> Amount of walltime to request for the job.
* `dry-run` -> Flag for dry-run. Produces the submission script without launching it.
* `dotenv-location` -> Location of the environment file (.env). Assumed to be the project root directory if not provided.
* `help` -> Show the CLI help message.

### 3.4 Example product outputs

An example output can be found on the NCI at `/g/data/yp75/projects/sar-antarctica-processing/example/data/processed_scene/S1A_EW_GRDM_1SSH_20250419T221041_20250419T221148_058831_074A60_9416`
* The scene was run with a spacing of 40m, with both linear and decibel scaling (denoted `_db`).
* The target CRS was set to be `3031`, original outputs (using CopDem) are denoted `_4326`, and all geocoded outputs are automatically repojected to the target CRS if different (denoted `_3031`).
* The `commands.sh` file shows the GAMMA commands that were run.

### 3.5 Logs and errors

The corresponding logs and submission script for the above example output can be found on the NCI at `/g/data/yp75/projects/sar-antarctica-processing/example/submission/logs/S1A_EW_GRDM_1SSH_20250419T221041_20250419T221148_058831_074A60_9416`
* `INFO` messages from sar-pipeline are sent to the `.ER` file
* command line messages, including the job summary, are sent to the `.OU` file

Errors to be aware of:
#### Out of memory
In the `.ER` file, you will see a message like 
```text
Job 154132534 has exceeded memory allocation on node gadi-cpu-clx-2232.gadi.nci.org.au
```
You should resubmit the job with a larger `--mem` value.

### 3.6 Troubleshooting
If processing a large number of scenes, the easiest way to check if they've all been processed is to re-submit the same CLI options with the `--dry-run` flag.
This will create a `missing_scenes_YYYY_MM_DD_HH_MM_SS.txt` in the output folder. 
If this file contains any scenes, you can then investigate the logs for those scenes and resubmit once the problem is resolved.

### 3.7 Setting permissions for external access

Typically, this pipeline is used to process EW scenes for selected users with NCI accounts. 
To ensure they can access their data, you must enable open access on the output folder using `chmod`.

When all scenes have been processed, run 
```bash
chmod -R +777 /path/to/output/directory
```
to ensure any NCI user with access to the project can read and copy the files.
You will need to re-run this if you add more processed scenes to an existing output directory.

## 4. Project setup

We recommend cloning the repository to a project folder that you own, where you have read, write and execution permissions.
In this documentation, we will use `/g/data/<project>/<username>`, where `project` is the project code (e.g. `yp75`) and `username` is your NCI username (typically your initials, followed by numbers).

### 4.1. Conda install

On NCI, it is recommended that you install Conda into a project, rather than your home directory, to save space.
The target install directory should be `/g/data/<project>/<username>`.

Run the following commands:
1. Get Miniforge installer
```bash
curl -sSL https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh -o miniforge.sh
```
2. Set the desired install location
```bash
export CONDA_PREFIX=/g/data/<project>/<username>/miniforge3
```
3. Add the Conda prefix to your path
```bash
export PATH=$CONDA_PREFIX/bin:$PATH
```
4. Install Conda via Miniforge
```bash
bash miniforge.sh -b -p $CONDA_PREFIX
```
5. Remove the installer
```bash
rm miniforge.sh
```
6. Initialise Conda
```bash
$CONDA_PREFIX/bin/conda init bash
```

### 4.2. Add required Conda environments
Once Conda is installed, make sure it's initialised (you should see `(base)` at the start of your terminal prompt), then, navigate to the `sar-pipeline repository`.

Run the following commands to install the required Conda environments:
`sar-pipeline`
```bash
conda env create -f environment.yaml && conda clean -afy
```
`pygssearch-env`
```bash
conda env create -f Conda/pygssearch/environment.yaml  && conda clean -afy
```

### 4.3. Update the Conda exe environment variable
Create a `.env` file based on the example and fill in the required environment variable values.
For `CONDA_EXE`, this should be set as `/g/data/<project>/<username>/miniforge3/bin/conda` if you followed the above instructions.

### 4.4. Set up symlink for GAMMA

The version of GAMMA currently used by the pipeline (20230712) requires a symlink for `libgdal.so.20`, as this lib file is not available in the Conda environment. 
The following steps are used to create the symlink:

1. Create a directory for symlinks
```bash
mkdir /g/data/<project>/<username>/gamma_symlinks
```
2. Identify the location of gdal library files in your Conda environement
```bash
cd /g/daya/<project>/<username>/miniforge3/envs/sar-pipeline/lib
find . -name "libgdal*"
```
3. Confirm that `./libgdal.so.36` appears in the list
4. Create the symlink
```bash
cd /g/data/<project>/<username>/gamma_symlinks
ls -s /g/data/<project>/<username>/miniforge3/envs/sar-pipeline/lib/libgdal.so.36 libgdal.so.20
```

You must supply an appropriate `gamma_env_var` path in the configuration file or at run time via the CLI. 
To ensure all lib files from the Conda environment are available, as well as the new symlink, use the following:
```toml
gamma_env_var = "/g/data/<project>/<username>/micromamba/envs/sar-pipeline/lib:/g/data/<project>/<username>/gamma_symlinks"
```

### 4.5 Initialise pyroSAR

The pyroSAR library is a python wrapper for various GAMMA command line utilities.
As such, it needs to read the GAMMA commands and create the appropriate Python wrapper functions before first use.

You can check whether it exists by seeing if you have a folder at `~/.pyrosar/gammaparse`.
If you do not have this folder, or you want to change your version of GAMMA or  which Conda install you're using, follow these steps:

1. Activate the sar-pipeline conda environment
```bash
conda activate sar-pipeline
```
2. Run a new Python REPL
```bash
python
```
3. Specify the required paths, set these as environment variables, then run the GAMMA `autoparse` function from pyroSAR:
```python
>>> gamma_lib_dir = "/g/data/dg9/GAMMA/GAMMA_SOFTWARE-20230712"
>>> gamma_env_var = "/g/data/<project>/<username>/micromamba/envs/sar-pipeline/lib:/g/data/<project>/<username>/gamma_symlinks"
>>> from sar_pipeline.utils.gamma import set_gamma_env_variables
>>> set_gamma_env_variables(gamma_lib_dir, gamma_env_var)
>>> from pyroSAR.gamma.parser import autoparse
>>> exit()
```
4. Check that the following files are available in your NCI home directory at `~/.pyrosar/gammaparse`:
```bash
diff.py
disp.py
__init__.py
isp.py
lat.py
msp.py
__pycache__
```

## 5. Examples

### 5.1. Running a single scene

### 5.2. Running a list of scenes

## 6. Development environment setup



<!-- ### Finding the location of a scene on the NCI
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
``` -->