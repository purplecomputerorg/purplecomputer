# Purple Computer Docker Image
# Simulates the full Purple Computer environment for testing

FROM ubuntu:22.04

# Prevent interactive prompts during package installation
ENV DEBIAN_FRONTEND=noninteractive

# Install system packages
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    ipython3 \
    colorama \
    git \
    curl \
    vim \
    && rm -rf /var/lib/apt/lists/*

# Install Python packages
RUN pip3 install --no-cache-dir \
    ipython \
    colorama \
    termcolor \
    packaging \
    traitlets \
    simple-term-menu

# Create purple user (no password, matches real setup)
RUN useradd -m -s /bin/bash purple && \
    passwd -l purple

# Create directory structure
RUN mkdir -p /home/purple/.purple/packs && \
    mkdir -p /home/purple/.purple/modes && \
    mkdir -p /home/purple/.ipython/profile_default/startup

# Copy Purple Computer files
COPY purple_repl/ /home/purple/.purple/

# Copy IPython startup files from single source of truth
RUN cp /home/purple/.purple/startup/*.py /home/purple/.ipython/profile_default/startup/

COPY packs/*.purplepack /tmp/packs/ 2>/dev/null || true

# Set ownership
RUN chown -R purple:purple /home/purple

# Switch to purple user
USER purple
WORKDIR /home/purple

# Install example packs
RUN if [ -f /tmp/packs/core-emoji.purplepack ]; then \
        cd /home/purple/.purple && \
        python3 -c "from pack_manager import PackManager, get_registry; from pathlib import Path; \
        manager = PackManager(Path('/home/purple/.purple/packs'), get_registry()); \
        manager.install_pack_from_file(Path('/tmp/packs/core-emoji.purplepack')); \
        print('Core emoji pack installed')"; \
    fi

RUN if [ -f /tmp/packs/education-basics.purplepack ]; then \
        cd /home/purple/.purple && \
        python3 -c "from pack_manager import PackManager, get_registry; from pathlib import Path; \
        manager = PackManager(Path('/home/purple/.purple/packs'), get_registry()); \
        manager.install_pack_from_file(Path('/tmp/packs/education-basics.purplepack')); \
        print('Education pack installed')"; \
    fi

# Set environment
ENV HOME=/home/purple
ENV IPYTHONDIR=/home/purple/.ipython

# Default command - run Purple Computer REPL
CMD ["python3", "/home/purple/.purple/repl.py"]
