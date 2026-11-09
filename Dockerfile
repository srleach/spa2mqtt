# syntax=docker/dockerfile:1
#
# spa2mqtt container image.
#
# Build:  docker build --build-arg VERSION=2.0.0 -t spa2mqtt .
# Run:    docker run -v ./config.yml:/app/config.yml:ro spa2mqtt
#
# The image reads its configuration from /app/config.yml (mount your file there).
# Environment variables (SPA_IP, MQTT_BROKER, ...) override the file. See config.yml.example.

ARG PYTHON_IMAGE=python:3.12-slim

# ---------------------------------------------------------------------------- build stage
# Build a wheel in a separate stage, so build tools do not end up in the final image.
FROM ${PYTHON_IMAGE} AS build

# The version normally comes from the git tag (hatch-vcs). The build context has no .git
# (see .dockerignore), so the release workflow passes the version in as a build argument.
ARG VERSION=0.0.0+local
# PyYAML has no prebuilt wheel for linux/arm/v7, so pip builds it from source there.
# PYYAML_FORCE_LIBYAML=0 selects the pure-Python build, which needs no C compiler.
ENV SETUPTOOLS_SCM_PRETEND_VERSION=${VERSION} \
    PYYAML_FORCE_LIBYAML=0 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /src
COPY pyproject.toml README.md ./
COPY spa2mqtt ./spa2mqtt
COPY definitions ./definitions
# Build wheels for the package and every dependency. The "serial" extra adds
# pyserial-asyncio, so a USB-RS485 adapter works without a custom image.
RUN pip wheel --wheel-dir /wheels ".[serial]"

# ---------------------------------------------------------------------------- runtime stage
FROM ${PYTHON_IMAGE}

ARG VERSION=0.0.0+local
ARG REVISION=unknown
LABEL org.opencontainers.image.title="spa2mqtt" \
      org.opencontainers.image.description="Bridge Balboa-family hot-tub RS485 buses to MQTT / Home Assistant" \
      org.opencontainers.image.source="https://github.com/srleach/spa2mqtt" \
      org.opencontainers.image.url="https://github.com/srleach/spa2mqtt" \
      org.opencontainers.image.documentation="https://seanrleach.co.uk/spa2mqtt/" \
      org.opencontainers.image.licenses="MIT" \
      org.opencontainers.image.version="${VERSION}" \
      org.opencontainers.image.revision="${REVISION}"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Install only from the wheels built above (--no-index), so this stage needs no network.
COPY --from=build /wheels /wheels
RUN pip install --no-index --find-links /wheels "spa2mqtt[serial]" && rm -rf /wheels

# Run as an unprivileged user. The bridge only needs network access and a read-only config.
# For a USB-RS485 adapter, pass the device and its group, for example:
#   --device /dev/ttyUSB0 --group-add dialout
RUN useradd --system --uid 10001 --no-create-home --home-dir /app --shell /usr/sbin/nologin spa2mqtt
WORKDIR /app
USER 10001:10001

# config.yml is read from /app/config.yml; mount it read-only at that path.
CMD ["spa2mqtt", "run", "-c", "/app/config.yml"]
