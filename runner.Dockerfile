FROM data.forgejo.org/forgejo/runner:13.0.0

USER root

RUN apk add --no-cache \
    nodejs \
    npm \
    bash \
    git \
    curl \
    gcompat \
    podman \
    docker-cli \
    python3 \
    py3-pip \
    py3-virtualenv \
    python3-dev \
    build-base

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | \
    env UV_INSTALL_DIR=/usr/local/bin sh

RUN uv --version

# Install Python 3.14
RUN uv python install 3.14

RUN uv python list

USER 1000:1000
