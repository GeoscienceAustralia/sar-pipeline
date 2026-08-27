#!/bin/bash
# Wrapper to run cli commands inside sar-pipeline conda env

# 1. Source conda
source $CONDA_PREFIX/etc/profile.d/conda.sh

# 2. Activate sar-pipeline environment
conda activate sar-pipeline

# 3. Run whatever CLI is passed as arguments
#    "$@" forwards all docker run args
exec "$@"