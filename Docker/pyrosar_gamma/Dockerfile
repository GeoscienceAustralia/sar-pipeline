FROM ubuntu:22.04

# Non-interactive mode for apt
ENV DEBIAN_FRONTEND=noninteractive

# Install required tools
RUN apt-get update && apt-get install -y \
    curl \
    wget \
    ca-certificates \
    bash \
    git \
    && rm -rf /var/lib/apt/lists/*

# Install Pixi using the official install script
RUN curl -fsSL https://pixi.sh/install.sh | sh

# Ensure Pixi is available on PATH 
ENV PATH="/root/.pixi/bin:${PATH}"

# copy files across to /app and install the environment with pixi
WORKDIR /app
COPY . /app
RUN chmod +x -R /app
RUN pixi install

# Run shell script for pyrosar-gamma inside the pixi env
ENTRYPOINT ["scripts/run_pyrosar_gamma_workflow.sh"]
CMD []

