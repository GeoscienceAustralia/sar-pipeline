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

> **_NOTE:_** If no evironment is specified, `pixi` will add the package to the `default` environment.
> If you only want to install it in the `dev` environment, add `--feature dev` to the commands below.

#### From Conda
We recommend using conda when possible.

To install a package from Conda, run `pixi add <package-name>`

Pixi defaults to using the `conda-forge` channel.
To add other channels, see [`pixi workspace channel`](https://pixi.sh/latest/reference/cli/pixi/workspace/channel/).

#### From Pypi
Some packages are only available on Pypi. 

To install a package from Pypi, run `pixi add --pypi <package-name>`

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

### Running tasks
The test suite consists of the following tasks:
* all tests: `pixi run test-all`
* nci filesystem tests: `pixi run test-nci-filesystem`
* pipeline tests: `pixi run test-pipeline`

There is also a task to export the `default` pixi environment as a conda environment.yml file: `pixi run export-conda`

## Pre-commit hooks
Sometimes, it's easy to miss updating the lock file, especially if you directly edit the `pyproject.toml` file. 
And, it's easy to forget to export a new version of the conda `environment.yml` file.
We have added the `pre-commit` package to manage these steps.

When you make a git commit, the following checks will be run:
* Is the `pixi.lock` file up to date with the `pyproject.toml` file?
* Is the `environment.yml` file up to date with the `pyproject.toml` file?

If either of these checks fail, the pre-commit hook will automatically update the files for you, and provide a message that you must add the changed files and re-run the commit step. 