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

## Install micromamba in the current directory:
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

## Install the required packages using environment.yml
Change directories to the cloned repository directory, then run
```
micromamba create -f environment.yml 
```

Activate the environment using
```
micromamba activate sar-pipleine
```

## Pip install the repository code
Once the environment is activated, install the source code in editable mode using
```
pip install -e .
```