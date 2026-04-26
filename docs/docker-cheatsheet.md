# Docker Cheatsheet — Images, Containers, Volumes, Cache & More

---

## Index

- [Images](#images)
- [Containers](#containers)
- [Volumes](#volumes)
- [Networks](#networks)
- [Build Cache](#build-cache)
- [System-wide Cleanup](#system-wide-cleanup)
- [Docker Compose](#docker-compose)
- [Context](#context-important-after-docker-desktop-removal)
- [Quick Disk Audit](#quick-disk-audit-run-these-first)

---

## Images

```bash
docker images                          # list all local images
docker images -a                       # include intermediate images
docker images --digests                # show image digests
docker image inspect <image>           # full metadata of an image
docker image history <image>           # layer-by-layer build history
docker pull <image>:<tag>              # pull image from registry
docker pull <image>:latest             # pull latest tag
docker rmi <image>                     # remove an image
docker rmi $(docker images -q)         # remove ALL images
docker rmi $(docker images -f "dangling=true" -q)  # remove untagged/dangling images
docker image prune                     # remove all dangling images
docker image prune -a                  # remove all unused images (not used by any container)
docker tag <source> <target>           # tag an image
docker save -o out.tar <image>         # export image to tar
docker load -i out.tar                 # import image from tar
```

---

## Containers

```bash
docker ps                              # list running containers
docker ps -a                           # list all containers (including stopped)
docker ps -q                           # only container IDs
docker ps -s                           # show container disk usage
docker inspect <container>             # full metadata
docker stats                           # live CPU/mem/net usage of all running containers
docker stats <container>               # stats for a specific container
docker top <container>                 # processes running inside container
docker logs <container>                # stdout/stderr logs
docker logs -f <container>             # follow logs (tail -f style)
docker logs --tail 100 <container>     # last 100 lines

docker start <container>               # start stopped container
docker stop <container>                # graceful stop
docker kill <container>                # force kill
docker restart <container>             # restart
docker pause <container>               # pause (freeze)
docker unpause <container>             # resume

docker rm <container>                  # remove stopped container
docker rm -f <container>               # force remove running container
docker rm $(docker ps -aq)             # remove ALL containers
docker container prune                 # remove all stopped containers

docker exec -it <container> bash       # shell into running container
docker exec -it <container> sh         # for alpine/minimal images
docker cp <container>:/path ./local    # copy file from container to host
docker cp ./local <container>:/path    # copy file from host to container
```

---

## Volumes

```bash
docker volume ls                       # list all volumes
docker volume inspect <volume>         # full metadata
docker volume create <name>            # create a named volume
docker volume rm <volume>              # remove a volume
docker volume prune                    # remove all unused volumes
```

---

## Networks

```bash
docker network ls                      # list all networks
docker network inspect <network>       # full metadata
docker network create <name>           # create a network
docker network rm <name>               # remove a network
docker network prune                   # remove unused networks
docker network connect <net> <container>     # attach container to network
docker network disconnect <net> <container>  # detach container from network
```

---

## Build Cache

```bash
docker builder ls                      # list builders
docker builder du                      # disk usage of build cache
docker buildx du                       # disk usage (buildx)
docker buildx prune                    # remove build cache
docker buildx prune -f                 # remove without confirmation prompt
docker buildx prune --all              # remove all build cache including in-use
docker system df                       # overall disk usage breakdown (images, containers, volumes, cache)
```

---

## System-wide Cleanup

```bash
docker system df                       # show disk usage
docker system df -v                    # verbose — per image/container/volume breakdown
docker system prune                    # remove stopped containers + dangling images + unused networks
docker system prune -a                 # + all unused images
docker system prune -a --volumes       # + volumes (WARNING: deletes data)
docker system prune -a --volumes -f    # same, no confirmation prompt
```

---

## Docker Compose

```bash
docker compose ps                      # list containers in current project
docker compose ps -a                   # include stopped
docker compose logs                    # logs for all services
docker compose logs -f <service>       # follow logs for one service
docker compose up -d                   # start in background
docker compose down                    # stop and remove containers + networks
docker compose down -v                 # + remove volumes
docker compose pull                    # pull latest images for all services
docker compose build                   # build images
docker compose config                  # validate and view merged config
```

---

## Context (important after Docker Desktop removal)

```bash
docker context ls                      # list all contexts
docker context show                    # current active context
docker context use default             # switch to default (Engine) context
docker context rm <name>               # remove a context
```

---

## Quick Disk Audit (run these first)

```bash
docker system df                       # summary
docker system df -v                    # full breakdown
docker builder du                      # build cache size
docker volume ls                       # check named volumes
docker images -a                       # all images including intermediates
docker ps -a -s                        # all containers with disk size
```
