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
    podman-compose \
    docker-cli \
    python3 \
    py3-pip \
    py3-virtualenv \
    python3-dev \
    build-base && \
    rm -f /etc/containers/seccomp.json

COPY --chown=1000:1000 src/ /usr/local/bin/

# Install uv
RUN curl -LsSf https://astral.sh/uv/install.sh | \
    env UV_INSTALL_DIR=/usr/local/bin sh && \
    uv --version && \ 
    uv python install 3.14 && \
    uv python list

USER 1000:1000
