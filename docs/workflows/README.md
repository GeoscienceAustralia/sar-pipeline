# Workflows
The repository will handle multiple workflows and backends, some of which have specific requirements.

## Workflows
- pyroSAR + GAMMA
    - [Requirements](pyrosar_gamma.md)

## Command line interface
> **_NOTE:_**  At this time, pyroSAR + GAMMA is the only workflow, and the command line interfaces have not yet been generalised to other workflows.

The package has a number of useful command line interfaces:

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