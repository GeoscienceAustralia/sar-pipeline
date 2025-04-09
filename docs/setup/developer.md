# Developer set up
On the NCI, complete these steps on a login node, as the installs require internet access.

## Clone the repository
On the NCI, navigate to the place you want to keep your development. Suggestions are:
- home directory: `~/`
- user directory in project: `/g/data/yp75/<nci-username>/`

Clone the repository into the chosen directory using
```
git clone https://github.com/GeoscienceAustralia/sar-pipleine.git
```

## Pixi

### Install pixi in home directory
Follow the [pixi installation guide](https://pixi.sh/latest/#installation).

Note that pixi updates regularly, as it is in active development, so regularly run `pixi self-update`

### Install pixi environments
Environments are associated with the project.

* The `default` environment contains packages required for the code base (e.g. gdal, rasterio).
* The `test` environment contains everything from the `default` environment, PLUS packages required for tests (e.g. pytest).

`cd` to the repository folder and install the environments:

To install both environments, run
```bash
pixi install --all
```

### Run a single command using pixi
For the default environment, use
```bash
pixi run <command>
```

For the `test` environment, use
```bash
pixi run -e test <command>
```

### Activate the environment
For longer sessions, you can activate the environment by running
```bash
pixi shell
```
or 
```bash
pixi shell -e test
```
To exit the shell, run 
```bash
exit
```

### Run tests

For the main pipeline code, run `pixi run pipeline_tests`

If on the NCI:
* For filesystem tests, run `pixi run nci_filesystem_tests`
* For all tests, run `pixi run tests`

### Export the environment.yml

Pixi can produce a conda environment file

Run `pixi run export_conda`

This can then be used for any other conda based package manager (e.g. micromamba)

### Add new dependencies to the environment

All dependencies explicitly called within the code should be added to the project. These can be viewed with `git grep -h import | sort | uniq`

To add a new dependency we rely on pixi:

1. add the required packages using `pixi add <package>` for conda distributed packages. Include `--pypi` if it's only available on pypi
    - E.g. `pixi add --pypi numpy` 

2. check the versions that were installed using `pixi list -x` (this shows the versions of packages explicitly listed in pyproject.toml

3. Check and manually update the versions in the `pyproject.toml` if required (remove upper limits from conda packages, add versions for pypi packages)

Export the update environment as described above

## Micromamba

### Install micromamba in the current directory:
Run `"${SHELL}" <(curl -L https://micro.mamba.pm/install.sh)` and provide the following answers to the prompts

- *Micromamba binary folder? [~/.local/bin]* `./micromamba/bin`
- *Init shell (bash)? [Y/n]* `Y`
- *Configure conda-forge? [Y/n]* Y
- *Prefix location? [~/micromamba]* ./micromamba

This will add this version of micromamba to your `~/.bashrc` file, so that it is initialised when you log in to NCI.

Run `source ~/.bashrc` to initialise the micromamba environment. This will be done automatically on future log ins.

Run `micromamba env list` to check if micromamba has been set up correctly. You should see:
```
  Name            Active  Path                                                                  
────────────────────────────────────────────────────
  base            *       /<install-path>/micromamba             
```

### Install the required packages using environment.yml
Change directories to the cloned repository directory, then run
```
micromamba create -f environment.yml 
```

Activate the environment using
```
micromamba activate sar-pipleine
```

### Pip install the repository code
Once the environment is activated, install the source code in editable mode using
```
pip install -e .
```