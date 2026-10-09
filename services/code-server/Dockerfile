# code-server with the Docker CLI, Compose and Buildx added. The CLI talks to
# the isolated code-server-docker (Docker-in-Docker) sidecar, never to the
# host's Docker. The CLI binaries are copied from Docker's official cli image
# so they match the sidecar's engine version exactly.
ARG DOCKER_VERSION
ARG CODE_SERVER_VERSION
FROM docker:${DOCKER_VERSION}-cli AS docker-cli

FROM codercom/code-server:${CODE_SERVER_VERSION}
COPY --from=docker-cli /usr/local/bin/docker /usr/local/bin/docker
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-compose /usr/local/libexec/docker/cli-plugins/docker-compose
COPY --from=docker-cli /usr/local/libexec/docker/cli-plugins/docker-buildx /usr/local/libexec/docker/cli-plugins/docker-buildx
