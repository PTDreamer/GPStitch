FROM ubuntu:24.04

LABEL maintainer="gopro-toolkit"
LABEL description="GPStitch web UI + gopro-dashboard-overlay CLI tools"

# ---------------------------------------------------------------------------
# Both repos are fetched from Git during build.
# Override with --build-arg to point to your own forks/branches.
#
#   docker build -f docker/Dockerfile \
#     --build-arg GOPRO_OVERLAY_REPO=https://github.com/you/gopro-dashboard-overlay \
#     --build-arg GOPRO_OVERLAY_REF=my-branch \
#     -t gopro-toolkit .
# ---------------------------------------------------------------------------
ENV PATH="/venv/bin:$PATH"

ARG GOPRO_OVERLAY_REPO=https://github.com/PTDreamer/gopro-dashboard-overlay.git
ARG GOPRO_OVERLAY_REF=main

ARG GPSTITCH_REPO=https://github.com/PTDreamer/GPStitch.git
ARG GPSTITCH_REF=main

# ---------------------------------------------------------------------------
# System dependencies
# ---------------------------------------------------------------------------
RUN apt-get update && apt-get install -y --no-install-recommends \
        curl gnupg unzip sudo git \
        fonts-noto fonts-roboto \
        ffmpeg \
        libcairo2-dev libraqm-dev pkg-config \
        gcc python3-dev \
        software-properties-common \
    && add-apt-repository -y ppa:deadsnakes/ppa \
    && apt-get update && apt-get install -y \
        python3.12 python3.12-venv python3.12-dev \
    && rm -rf /var/lib/apt/lists/*

# ---------------------------------------------------------------------------
# Python venv
# ---------------------------------------------------------------------------
RUN python3.12 -m venv /venv \
    && /venv/bin/pip install --upgrade pip setuptools wheel

# ---------------------------------------------------------------------------
# Clone & install gopro-overlay (the CLI engine)
# ---------------------------------------------------------------------------
RUN git clone --depth 1 --branch "${GOPRO_OVERLAY_REF}" \
        "${GOPRO_OVERLAY_REPO}" /src/gopro-overlay

WORKDIR /src/gopro-overlay
RUN /venv/bin/pip install ".[cairo]"

# ---------------------------------------------------------------------------
# Clone & install GPStitch (the web UI)
# ---------------------------------------------------------------------------
RUN git clone --depth 1 --branch "${GPSTITCH_REF}" \
        "${GPSTITCH_REPO}" /src/gpstitch

WORKDIR /src/gpstitch
RUN /venv/bin/pip install ".[cairo]"

# ---------------------------------------------------------------------------
# Runtime setup
# ---------------------------------------------------------------------------
EXPOSE 8000

VOLUME /work
WORKDIR /work

COPY docker/entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

ENTRYPOINT ["/entrypoint.sh"]
CMD ["gpstitch"]
