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

# Install additional dependencies for pyrosar-gamma
RUN apt-get update
RUN apt-get install -y libsqlite3-dev libzstd-dev libwebp-dev libjson-c-dev libgtk-3-0

# Set any necessary environment variables for pyrosar-gamma
ENV GAMMA_HOME="/usr/local/GAMMA_SOFTWARE-20230712"

# Create directory for symlinks and create a symlink to the first libgdal match found under /app
RUN set -eux; \
    mkdir -p /root/gamma_symlinks; \
    cd /root/gamma_symlinks; \
    TARGET="$(find /app -name 'libgdal.so.*' -print -quit)"; \
    if [ -z "$TARGET" ]; then \
      echo "No libgdal found under /app; creating a placeholder symlink to /dev/null"; \
      ln -sf /dev/null libgdal.so.20; \
    else \
      ln -sf "$TARGET" libgdal.so.20; \
    fi; \
    echo "Symlink created: $(readlink -f libgdal.so.20)"; \
    mkdir -p /root/.pyrosar/gammaparse; \
    chmod -R 777 /root/.pyrosar/gammaparse

# Set the LD_LIBRARY_PATH so that pyrosar-gamma can find the correct libgdal. This is to create the correct python bindings for pyrosar-gamma 
# inside .pyrosar folder to work with the correct version of gdal, which is installed in the pixi environment. 
# The symlink ensures that even if the exact version of libgdal changes, pyrosar-gamma will still find it correctly. 
# The /root/gamma_symlinks directory is added to LD_LIBRARY_PATH to ensure that the symlinked libgdal is found before any other versions that might be present in the system.
ENV LD_LIBRARY_PATH="/app/.pixi/envs/default/lib:/root/gamma_symlinks"

# Run shell script for pyrosar-gamma inside the pixi env
ENTRYPOINT ["scripts/run_pyrosar_gamma_workflow.sh"]
CMD []

