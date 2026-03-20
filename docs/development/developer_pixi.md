# Developer set up

These instructions cover how to install the package from source using pixi, which supports additional dependancies needed in development.
Key examples are packages related to testing and pre-commit steps.

> **_NOTE:_**  On the NCI, complete these steps on a login node, as the installs require internet access.

## Package management
Python packages are challenging! 
We have put some thought into how we manage them for both development and general use.

For developers, we have picked [`pixi`](https://pixi.sh/latest/).
This is because:
* It allows us to keep track of explicit python dependencies from both conda and pypi using a single `pyproject.toml` file.
* It keeps a [lock file](https://pixi.sh/latest/workspace/lockfile/) that is always up-to-date, allowing for reproducible environments.
* It allows us to keep packages needed for development in their own [environment](https://pixi.sh/latest/workspace/environment/).
* It allows us to define useful [tasks](https://pixi.sh/latest/workspace/advanced_tasks/) (similar to a Makefile) all within the `pyproject.toml` file.

Follow the steps below, and refer back to them as needed.

> [!IMPORTANT]
> We recommend using pixi for all package management

## First time set up

### Install pixi in home directory
Follow the [pixi installation guide](https://pixi.sh/latest/#installation).

Note that pixi updates regularly, as it is in active development, so regularly run `pixi self-update`

### Install pixi environments
Environments are associated with the project.

* The `default` environment contains packages required for the code base (e.g. gdal, rasterio).
* The `dev` environment contains everything from the `default` environment, PLUS packages required for tests (e.g. pytest, coverage) and pre-commit hooks (pre-commit).

`cd` to the repository folder and install the environments:

To install both environments, run
```bash
pixi install --all
```

### Set up pre-commit hooks
We have a number of pre-commit actions that will check your environment related files are up to date before allowing you to commit.
The first time you set up the repo, install the pre-commit hooks by running 

```bash
 pixi run -e dev pre-commit install
 ```

 This will set up the [required git hook scripts](https://pre-commit.com/#3-install-the-git-hook-scripts). 

## Developing with pixi
There are a few things to keep in mind when using `pixi`:

* The pixi environments are tied to the project, rather than globally installed.
* The best way to add new packages is to use `pixi add` because this will automatically update the lock file.
* Take advantage of pixi tasks to speed up your development workflow!

With this in mind, the following sections cover various how-to's for our development environment:

* [Add packages](#adding-a-package)
* [Keep the pyproject.yml file tidy](#tidying-up-the-pyprojecttoml-file)
* [Run commands](#running-commands)
* [Create and run tasks](#creating-and-running-tasks)
* [Using pre-commit hooks](#pre-commit-hooks)

### Adding a package

We recommend using [`pixi add`](https://pixi.sh/latest/reference/cli/pixi/add/) because this will automatically update the lock file (`pixi.lock`).

> **_NOTE:_** If no environment is specified, `pixi` will add the package to the `default` environment.
> If you only want to install it in the `dev` environment, add `--feature dev` to the commands below.

#### From Pypi
Preference should be made to install packages from PyPi if they are available.
This is likely for common python packages.

To install or update a package from Pypi, run `pixi add --pypi <package-name>`

To remove a package from Pypi, run `pixi remove --pypi <package-name>`

#### From Conda
If the package is not available on PyPi, conda should be used.

To install a package from Conda, run `pixi add <package-name>`

Pixi defaults to using the `conda-forge` channel.
To add other channels, see [`pixi workspace channel`](https://pixi.sh/latest/reference/cli/pixi/workspace/channel/).


#### Directly editing the pyproject.toml file
You can manually add packages by adding them to the appropriate section of the `pyproject.toml` file:
* `[tool.pixi.dependencies]` for Conda
* `dependencies` for pip

However, this will not automatically update the `pixi.lock` file, so is not recommended.

## Tidying up the pyproject.toml file
After adding a package, it is worth doing a little extra work to make sure the `pyproject.toml` file is nicely formatted:

1. check the versions that were installed using `pixi list -x` (this shows the versions of packages explicitly listed in `pyproject.toml`)

1. Check and manually update the versions in the `pyproject.toml` if required (remove upper limits from conda packages, add versions for pypi packages)

### Checking all the packages you've imported are in the `pyproject.toml`

All dependencies explicitly called within the code should be added to the project. These can be viewed with `git grep -h import | sort | uniq`

## Pre-commit hooks
Sometimes, it's easy to miss updating the lock file, especially if you directly edit the `pyproject.toml` file. 
And, it's easy to forget to export a new version of the conda `environment.yaml` file.
We have added the `pre-commit` package to manage these steps.

When you make a git commit, the following checks will be run:
* Is the `pixi.lock` file up to date with the `pyproject.toml` file?
* Is the `environment.yaml` file up to date with the `pyproject.toml` file?

If either of these checks fail, the pre-commit hook will automatically update the files for you, and provide a message that you must add the changed files and re-run the commit step. 

## Running commands
You have two options for running commands
* [`pixi run <command>`](http://pixi.sh/latest/reference/cli/pixi/run/) will run the command in the environment as a once-off action
* [`pixi shell <command>`](https://pixi.sh/latest/reference/cli/pixi/shell/) will activate an environment, similar to how conda works

Every time you run a command, `pixi` will run a solve on the environment. 
This ensures packages are kept up to date with what's declared in the `pyproject.toml` file. 

### Selecting an environment
You can chose the environment you run in by passing `-e <environment>` to either of the run commands. For example
```bash
pixi run -e dev pytest
```

If you pass nothing, the command will be run in the `default` environment. 

## Creating and running tasks
Pixi allows you to define tasks tied to particular environments.
This allows us to define short-cut commands to run our test suite, without having to explicitly invove the `dev` environment. 

### Creating tasks
See the [pixi documentation](https://pixi.sh/latest/workspace/advanced_tasks/) and [pixi cli](https://pixi.sh/latest/reference/cli/pixi/task/).

### Running tasks, the sar-pipeline cli and tests

```bash
pixi run <taskname>
```
can be used to run tasks defined in the pyproject.toml. 
This includes accessing the sar-pipeline command line utilities (CLI) and 
tests for the codebase. 

### Running utility tasks

The following utility tasks can be run.

* `pixi run export-conda` -> Export the `default` pixi environment as a conda environment.yaml file
* `pixi run lint` -> Applies the black formatter to the project files
* `pixi run install-pygssearch-env` -> installs the pygssearch conda environment. Required to download data from the aus cop hub.


### Running the cli
  
pixi also provides access to command line interfaces defined in the sar-pipeline code.
These can be found listed in the pyproject.toml under the `[project.scripts]` section.
These have been separated into different sections based on their functions.
To understand their function, the following can be run to access the docs:

```bash
pixi run <cli> --help
```

For example:

```bash
>>> pixi run get-burst-ids-for-scene --help`

Usage: get-burst-ids-for-scene [OPTIONS]

  Get the unique burst IDs for a given scene.

Options:
  --scene TEXT                 Scene to get the list of bursts ids for. e.g. S
                               1A_IW_SLC__1SSH_20220101T124744_20220101T124814
                               _041267_04E7A2_1DAD  [required]
  --save-geometries DIRECTORY  Folder to save the geometries to as a geojson.
                               Useful for visualisation of burst locations.
                               Path will be
                               {save_geometries}/{scene}_burst_geoms.json
  --help                       Show this message and exit.
```

The CLI's are:

```python
[project.scripts]
### GENERAL ###
upload-files-in-folder-to-s3 = "sar_pipeline.pipelines.pyrosar_gamma.cli:upload_files_in_folder_to_s3"
get-burst-ids-for-scene = "sar_pipeline.pipelines.isce3_rtc.cli:get_bursts_ids_for_scene"
download-etad = "sar_pipeline.preparation.cli:download_etad"
### NCI / PYROSAR_GAMMA ###
find-scene = "sar_pipeline.pipelines.pyrosar_gamma.cli:find_scene_file"
find-orbits = "sar_pipeline.pipelines.pyrosar_gamma.cli:find_orbits_for_scene"
run-pyrosar-gamma-workflow = "sar_pipeline.pipelines.pyrosar_gamma.cli:run_pyrosar_gamma_workflow"
submit-pyrosar-gamma-workflow = "sar_pipeline.pipelines.pyrosar_gamma.cli:submit_pyrosar_gamma_workflow"
## ISCE3_RTC ###
isce3-rtc-get-data-for-scene-and-make-run-config = "sar_pipeline.pipelines.isce3_rtc.cli:get_data_for_scene_and_make_run_config"
isce3-rtc-make-metadata-and-upload-bursts = "sar_pipeline.pipelines.isce3_rtc.cli:make_metadata_and_upload_bursts"
isce3-rtc-compare-products = "sar_pipeline.pipelines.isce3_rtc.cli:compare_products"
```

## Running Tests

Tests for the pipeline are run in a similar way. The tests are similarly split into sections
considering the pipeline, and if credentials are required. The block below shows the
available tests.

1. The shared tests that do not require credentials should be fun first for all pipelines
2. pipeline specific tests can then be run. Note that the environment variables in the [.env.example](../../.env.example) will need to be set for full functionality. For example, this will ensure data can be downloaded from the available providers, and products can be uploaded as intended.

```python
[tool.pixi.feature.dev.tasks]
### TEST RELATED TASKS ###
# run all tests
test-all = "pytest"

### Shared Pipeline Tests ###
# tests do not require credentials - can currently be run locally and in github
test-pipeline-no-creds = 'pixi run install-pygssearch-env && export PYGSSEARCH_CONDA_ENV="$(conda info --base)/envs/pygssearch-env" && pytest tests/sar_pipeline/ --ignore=tests/sar_pipeline/isce3_rtc'
test-scene-data-source-queries='pixi run install-pygssearch-env && export PYGSSEARCH_CONDA_ENV="$(conda info --base)/envs/pygssearch-env" && pytest tests/sar_pipeline/test_scenes.py -o log_cli=true --capture=tee-sys --log-cli-level=INFO -v -s'

### ISCE3_RTC Pipeline Tests ###
# Tests require credentials - not currently setup for github but should be run locally before PRs
test-isce3-rtc = "pytest tests/sar_pipeline/isce3_rtc -o log_cli=true --capture=tee-sys --log-cli-level=INFO -v -s"
test-isce3-rtc-full-docker-workflow-run = "pixi run export-conda && pytest tests/sar_pipeline/isce3_rtc/test_full_docker_workflow_run.py -o log_cli=true --capture=tee-sys --log-cli-level=INFO -v -s"
test-isce3-rtc-burst-utils = "pytest tests/sar_pipeline/isce3_rtc/test_burst_utils.py -o log_cli=true --capture=tee-sys --log-cli-level=INFO -v -s"
test-isce3-rtc-cli-make-metadata-and-upload-bursts = "pytest tests/sar_pipeline/isce3_rtc/test_cli_make_metadata_and_upload_bursts.py -o log_cli=true --capture=tee-sys --log-cli-level=INFO -v -s"
test-isce3-rtc-cli-get-data-for-scene-and-make-run-config = "pytest tests/sar_pipeline/isce3_rtc/test_cli_get_data_for_scene_and_make_run_config.py -o log_cli=true --capture=tee-sys --log-cli-level=INFO -v -s"
test-isce3-rtc-downloads= 'pixi run install-pygssearch-env && export PYGSSEARCH_CONDA_ENV="$(conda info --base)/envs/pygssearch-env" && pytest tests/sar_pipeline/isce3_rtc/test_downloads.py -o log_cli=true --capture=tee-sys --log-cli-level=INFO -v -s'

### NCI Pipeline Tests ###
# nci specific tests that should be run locally on the nci
test-nci-filesystem = "pytest tests/filesystem"
```

### NCI / PyroSAR GAMMA tests

The following credentials must be set in a `.env` file at the project 
root for a complete test of code functionality :

```text
# Variables used on NCI only
CONDA_EXE=<determine from [setup](../pipelines/pyrosar_gamma.md) >
NCI_API_SCENE_FILE_LOCATION=/g/data/fj7/DEAnt/Sentinel-1
NCI_API_ORBIT_FILE_LOCATION=/g/data/fj7/CopHub/Sentinel-1
NCI_FILESYSTEM_FILE_LOCATION=/g/data/fj7/Copernicus/Sentinel-1/C-SAR/
```

Run the shared tests and then run the NCI specific tests that will test the file system:

```bash
pixi run test-nci-filesystem
```

### ISCE3 Tests

More on testing is provided in the [isce3_rtc](../pipelines/isce3_rtc.md) docs.

The following credentials must be set in a `.env` file at the project 
root for a complete test of code functionality :

```text
EARTHDATA_LOGIN=
EARTHDATA_PASSWORD=
AWS_ACCESS_KEY_ID=
AWS_SECRET_ACCESS_KEY=
AWS_SESSION_TOKEN=
AWS_DEFAULT_REGION=
CDSE_LOGIN=
CDSE_PASSWORD=
AUS_COP_HUB_LOGIN=
AUS_COP_HUB_PASSWORD=
AUS_COP_HUB_CLIENT_ID=odata
AUS_COP_HUB_CLIENT_SECRET=
```

Note - The following variable will be automatically set by the task:

```test
PYGSSEARCH_CONDA_ENV
```

All of the isce3 related tests can then be run with

```bash
pixi run test-isce3-rtc
```

Note - The following test may take 1-2 hours, as it builds and runs the docker image, 
creates NRB (RTC_S1) and Static Layers (RTC_S1_STATIC), and compares those to
Benchmark data stored on AWS - https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/index.html?prefix=persistent/repositories/sar-pipeline/tests/sar_pipeline/isce3_rtc/results/