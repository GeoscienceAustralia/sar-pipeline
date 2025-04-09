# Geoscience Australia OPERA/RTC ISCE3 Sentinel-1 Pipeline Dockerfile
# Extension of - https://github.com/opera-adt/RTC/blob/main/Docker/Dockerfile

FROM oraclelinux:9

LABEL author="Geoscience Australia" \
description="ISCE3/RTC Pipeline Version 0.1" \
version="0.1"

RUN yum -y update &&\
yum -y install curl &&\
adduser rtc_user

RUN mkdir -p /home/rtc_user/OPERA

RUN chmod -R 755 /home/rtc_user &&\
chown -R rtc_user:rtc_user /home/rtc_user/OPERA

USER rtc_user

ENV CONDA_PREFIX=/home/rtc_user/miniconda3

# Install Miniconda
WORKDIR /home/rtc_user
RUN curl -sSL https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh -o miniconda.sh &&\
bash miniconda.sh -b -p ${CONDA_PREFIX} &&\
rm $HOME/miniconda.sh

ENV PATH=${CONDA_PREFIX}/bin:${PATH}
RUN ${CONDA_PREFIX}/bin/conda init bash

# Download the opera-adt/RTC code - UPDATE VERSION AND TAG HERE IF NEEDED
ARG RTC_VERSION=RTC-1.0.2
ARG RTC_VERSION_TAG=v1.0.2
RUN  curl -sSL https://github.com/opera-adt/RTC/archive/refs/tags/$RTC_VERSION_TAG.tar.gz -o $RTC_VERSION.tar.gz &&\
tar -xvf $RTC_VERSION.tar.gz -C OPERA &&\
rm $RTC_VERSION.tar.gz

# Create RTC CONDA environment
RUN conda create --name "RTC" --file /home/rtc_user/OPERA/$RTC_VERSION/Docker/lockfile.lock &&  conda clean -afy

SHELL ["conda", "run", "-n", "RTC", "/bin/bash", "-c"]

WORKDIR /home/rtc_user/OPERA

# Install OPERA s1-reader
RUN curl -sSL https://github.com/isce-framework/s1-reader/archive/refs/tags/v0.2.4.tar.gz -o s1_reader_src.tar.gz &&\
tar -xvf s1_reader_src.tar.gz &&\
ln -s s1-reader-0.2.4 s1-reader &&\
rm s1_reader_src.tar.gz &&\
python -m pip install ./s1-reader

# installing OPERA RTC
RUN python -m pip install ./$RTC_VERSION

# Download the burst-db, this is created using scripts/make_upload_burst_db.sh
WORKDIR /home/rtc_user/burst_db
ARG BURST_DB_URL="https://deant-data-public-dev.s3.ap-southeast-2.amazonaws.com/persistent/burst_db/0.9.0/opera-burst-bbox-only.sqlite3"
RUN curl -o opera-burst-bbox-only.sqlite3 "$BURST_DB_URL"

# Copy the full project and create a second CONDA environment for the sar-pipeline
WORKDIR /home/rtc_user/sar-pipeline
COPY --chown=rtc_user:rtc_user . /home/rtc_user/sar-pipeline
RUN conda env create -f /home/rtc_user/sar-pipeline/environment.yml

# Copy the .sh file that will be run on entry to the container
RUN mkdir -p /home/rtc_user/scripts
COPY --chown=rtc_user:rtc_user ./scripts/run_aws_pipeline.sh /home/rtc_user/scripts
RUN chmod +x /home/rtc_user/scripts/run_aws_pipeline.sh 

WORKDIR /home/rtc_user/working

# ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "sar-pipeline"]
ENTRYPOINT ["/home/rtc_user/scripts/run_aws_pipeline.sh"]