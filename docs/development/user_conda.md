# User set up

These instructions cover how to install the package from source using a conda installer.
In this case, we recommend micromamba, but any package manager that supports conda can be used.

## First time set-up 

### Install micromamba
Run `"${SHELL}" <(curl -L https://micro.mamba.pm/install.sh)`

> **_NOTE:_**  If running on the NCI, we recommend providing the following answers to the prompts:
> - *Micromamba binary folder? [~/.local/bin]* `./micromamba/bin`
> - *Init shell (bash)? [Y/n]* `Y`
> - *Configure conda-forge? [Y/n]* Y
> - *Prefix location? [~/micromamba]* ./micromamba

This will add this version of micromamba to your `~/.bashrc` file, so that it is when you start a new terminal session.

Run `source ~/.bashrc` to initialise the micromamba environment immediately after install.

Run `micromamba env list` to check if micromamba has been set up correctly. You should see:
```
  Name            Active  Path                                                                  
────────────────────────────────────────────────────
  base            *       /<install-path>/micromamba             
```

### Install the required packages using environment.yaml
Change directories to the cloned repository directory, then run
```bash
micromamba create -f environment.yaml 
```

Activate the environment using
```bash
micromamba activate sar-pipleine
```

The source package will be installed in editable mode.
However, we recommend you don't make changes to the source code when working with a conda package manager, and [use pixi instead](developer.md).