# OPERA/RTC ISCE3 Dockerfile
# Inspired by - https://github.com/opera-adt/RTC/blob/main/Docker/Dockerfile

FROM oraclelinux:9

LABEL author="Geoscience Australia" \
description="ISCE3/RTC Version 0.1" \
version="0.1"

RUN yum -y update &&\
yum -y install curl &&\
adduser rtc_user

RUN mkdir -p /home/rtc_user/OPERA

RUN chmod -R 755 /home/rtc_user &&\
chown -R rtc_user:rtc_user /home/rtc_user/OPERA

USER rtc_user

ENV CONDA_PREFIX=/home/rtc_user/miniconda3

# install Miniconda
WORKDIR /home/rtc_user
RUN curl -sSL https://repo.continuum.io/miniconda/Miniconda3-latest-Linux-x86_64.sh -o miniconda.sh &&\
bash miniconda.sh -b -p ${CONDA_PREFIX} &&\
rm $HOME/miniconda.sh

ENV PATH=${CONDA_PREFIX}/bin:${PATH}
RUN ${CONDA_PREFIX}/bin/conda init bash

# get the opera-adt/RTC code - UPDATE VERSION HERE
RUN  curl -sSL https://github.com/opera-adt/RTC/archive/refs/tags/v1.0.2.tar.gz -o RTC-1.0.2.tar.gz &&\
tar -xvf RTC-1.0.2.tar.gz -C OPERA &&\
rm RTC-1.0.2.tar.gz

# copy RTC source code and set rtc_user as owner
#COPY --chown=rtc_user:rtc_user . /home/rtc_user/OPERA/RTC

# create CONDA environment
RUN conda create --name "RTC" --file /home/rtc_user/OPERA/RTC-1.0.2/Docker/lockfile.lock &&  conda clean -afy

SHELL ["conda", "run", "-n", "RTC", "/bin/bash", "-c"]

WORKDIR /home/rtc_user/OPERA

# installing OPERA s1-reader
RUN curl -sSL https://github.com/isce-framework/s1-reader/archive/refs/tags/v0.2.4.tar.gz -o s1_reader_src.tar.gz &&\
tar -xvf s1_reader_src.tar.gz &&\
ln -s s1-reader-0.2.4 s1-reader &&\
rm s1_reader_src.tar.gz &&\
python -m pip install ./s1-reader

# installing OPERA RTC
RUN python -m pip install ./RTC-1.0.2 &&\
echo "conda activate RTC" >> /home/rtc_user/.bashrc

WORKDIR /home/rtc_user/sar-pipeline
# Install the GA pipeline code - copy and set rtc_user as owner
COPY --chown=rtc_user:rtc_user . /home/rtc_user/sar-pipeline
# Update the RTC pipeline with dependancies for the sar-pipeline
#RUN conda env update --name RTC --file /home/rtc_user/sar-pipeline/environment.yml
RUN python -m pip install .

WORKDIR /home/rtc_user/scratch

ENTRYPOINT ["conda", "run", "--no-capture-output", "-n", "RTC"]
# conda run --no-capture-output -n RTC