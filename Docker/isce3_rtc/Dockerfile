# Geoscience Australia OPERA/RTC ISCE3 Sentinel-1 Pipeline Dockerfile
# Extension of - https://github.com/opera-adt/RTC/blob/main/Docker/Dockerfile

FROM oraclelinux:9

LABEL author="Geoscience Australia" \
      description="Sentinel-1 IW NRB pipeline using NASA JPL opera/RTC" 

RUN yum -y update &&\
yum -y install curl &&\
yum install git -y &&\
adduser rtc_user

RUN mkdir -p /home/rtc_user/OPERA

RUN chmod -R 755 /home/rtc_user &&\
chown -R rtc_user:rtc_user /home/rtc_user/OPERA

USER rtc_user

# Install Miniforge
WORKDIR /home/rtc_user
ENV CONDA_PREFIX=/home/rtc_user/miniforge3
ENV PATH=$CONDA_PREFIX/bin:$PATH

RUN curl -sSL https://github.com/conda-forge/miniforge/releases/latest/download/Miniforge3-Linux-x86_64.sh -o miniforge.sh &&\
    bash miniforge.sh -b -p $CONDA_PREFIX &&\
    rm miniforge.sh &&\
    $CONDA_PREFIX/bin/conda init bash

# Download and install the Geoscience Australia fork of the opera/RTC project
# UPDATE VERSION AND TAG HERE IF NEEDED
# Install RTC from branch enable_ew_processing
ARG RTC_VERSION=RTC-enable_ew_processing
RUN curl -sSL https://github.com/GeoscienceAustralia/RTC/archive/refs/heads/enable_ew_processing.tar.gz -o $RTC_VERSION.tar.gz &&\
tar -xvf $RTC_VERSION.tar.gz -C OPERA &&\
rm $RTC_VERSION.tar.gz

# Create RTC CONDA environment
RUN conda create --name "RTC" --file /home/rtc_user/OPERA/$RTC_VERSION/Docker/lockfile.lock &&  conda clean -afy

SHELL ["conda", "run", "-n", "RTC", "/bin/bash", "-c"]

WORKDIR /home/rtc_user/OPERA

# Install OPERA s1-reader
# Install s1-reader from branch ew_mode_slc_support
RUN curl -sSL https://github.com/abradley60/s1-reader/archive/refs/heads/ew_mode_slc_support.tar.gz -o s1_reader_src.tar.gz &&\
tar -xvf s1_reader_src.tar.gz &&\
ln -s s1-reader-ew_mode_slc_support s1-reader &&\
rm s1_reader_src.tar.gz &&\
python -m pip install ./s1-reader

# Installing OPERA RTC
RUN python -m pip install ./$RTC_VERSION

# Download the burst-db. this is created using scripts/make_upload_iw_ew_burst_db.sh
ARG BURST_DB_VERSION_TAG=0.18.0
WORKDIR /home/rtc_user/burst_db

# Download both IW and EW burst-db files from the same base path
ARG BURST_DB_BASE_URL="https://dea-public-data-dev.s3.ap-southeast-2.amazonaws.com/projects/s1_nrb/burst_db/$BURST_DB_VERSION_TAG"
RUN if ! curl -f -o opera-iw-burst-bbox-only.sqlite3 "$BURST_DB_BASE_URL/opera-iw-burst-bbox-only.sqlite3"; then \
      echo "ERROR: IW burst_db not found at $BURST_DB_BASE_URL/opera-iw-burst-bbox-only.sqlite3"; \
      echo "This file can be be created an uploaded using scripts/make_upload_iw_ew_burst_db.sh"; \
      exit 1; \
    fi
RUN if ! curl -f -o opera-ew-burst-bbox-only.sqlite3 "$BURST_DB_BASE_URL/opera-ew-burst-bbox-only.sqlite3"; then \
      echo "ERROR: EW burst_db not found at $BURST_DB_BASE_URL/opera-ew-burst-bbox-only.sqlite3"; \
      echo "This file can be be created an uploaded using scripts/make_upload_iw_ew_burst_db.sh"; \
      exit 1; \
    fi

# Copy the full project and create a second CONDA environment for the sar-pipeline
WORKDIR /home/rtc_user/sar-pipeline
COPY --chown=rtc_user:rtc_user . /home/rtc_user/sar-pipeline
RUN echo "Installing sar-pipeline from environment.yaml, ensure dependencies have been updated if required."
RUN conda env create -f /home/rtc_user/sar-pipeline/environment.yaml && conda clean -afy

# Create third conda environment for pygssearch. Installed outside of sar-pipeline due to package conflicts. 
# This is required for downloading data from AUS_COP_HUB and will be called by a subprocess in the scene download function.
RUN conda env create -f /home/rtc_user/sar-pipeline/Conda/pygssearch/environment.yaml && conda clean -afy

# set the conda environment as a path
ENV PYGSSEARCH_CONDA_ENV=$CONDA_PREFIX/envs/pygssearch-env

# Copy all scripts into the container and make them executable
RUN mkdir -p /home/rtc_user/scripts
COPY --chown=rtc_user:rtc_user ./scripts/ /home/rtc_user/scripts/
RUN chmod +x /home/rtc_user/scripts/*

# Set working directory to the scripts folder
WORKDIR /home/rtc_user/scripts

# Set the default entrypoint to be the main pipeline script
ENTRYPOINT ["./run_isce3_rtc_pipeline.sh"]
CMD []