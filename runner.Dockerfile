FROM data.forgejo.org/forgejo/runner:13.0.0
USER root
RUN apk add --no-cache nodejs npm bash git curl gcompat podman docker-cli
USER 1000:1000