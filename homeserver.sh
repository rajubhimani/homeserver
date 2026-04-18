#!/bin/sh
# homeserver.sh — manage all homeserver services
#
# Usage:
#   ./homeserver.sh <env> <up|down|logs> <service|all> [service2 ...] [--profile <name>]
#
# Examples:
#   ./homeserver.sh dev up all
#   ./homeserver.sh prod up all
#   ./homeserver.sh dev up landing mealie
#   ./homeserver.sh prod up nextcloud immich jellyfin
#   ./homeserver.sh dev down all
#   ./homeserver.sh dev down landing mealie
#   ./homeserver.sh dev up immich --profile ml
#   ./homeserver.sh dev down immich --profile ml
#   ./homeserver.sh dev logs immich

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"

ALL_SERVICES="nginx nextcloud immich landing jellyfin vaultwarden paperless stirling-pdf mealie gitea uptime-kuma dozzle"

# Colors
GREEN="\033[0;32m"
RED="\033[0;31m"
YELLOW="\033[1;33m"
CYAN="\033[0;36m"
BOLD="\033[1m"
RESET="\033[0m"

info()    { printf "${CYAN}▶ %s${RESET}\n" "$*"; }
success() { printf "${GREEN}✔ %s${RESET}\n" "$*"; }
error()   { printf "${RED}✖ %s${RESET}\n" "$*"; }
warn()    { printf "${YELLOW}⚠ %s${RESET}\n" "$*"; }
header()  { printf "\n${BOLD}%s${RESET}\n\n" "$*"; }

base_file() {
  [ "$1" = "landing" ] && echo "docker-compose.yml" || echo "compose.yml"
}

is_valid_service() {
  for s in $ALL_SERVICES; do
    [ "$s" = "$1" ] && return 0
  done
  return 1
}

# Build -f flags: base + env overlay
compose_files() {
  service=$1
  env=$2
  dir="$BASE_DIR/$service"
  base=$(base_file "$service")
  files="-f $dir/$base"
  [ -f "$dir/compose.${env}.yml" ] && files="$files -f $dir/compose.${env}.yml"
  echo "$files"
}

# Build -f flags for down: base + all overlays to ensure full cleanup
compose_files_all() {
  service=$1
  dir="$BASE_DIR/$service"
  base=$(base_file "$service")
  files="-f $dir/$base"
  for e in dev prod; do
    [ -f "$dir/compose.${e}.yml" ] && files="$files -f $dir/compose.${e}.yml"
  done
  echo "$files"
}

do_up() {
  service=$1
  env=$2
  profile=$3
  dir="$BASE_DIR/$service"

  if [ ! -d "$dir" ]; then
    error "Service '$service' not found"
    return 1
  fi

  files=$(compose_files "$service" "$env")

  if [ -n "$profile" ]; then
    info "Starting $service ($env) --profile $profile..."
    docker compose $files --profile "$profile" up -d
  else
    info "Starting $service ($env)..."
    docker compose $files up -d
  fi

  if [ $? -eq 0 ]; then
    success "$service started"
  else
    error "$service failed to start"
  fi
}

do_down() {
  service=$1
  env=$2
  profile=$3
  dir="$BASE_DIR/$service"

  if [ ! -d "$dir" ]; then
    error "Service '$service' not found"
    return 1
  fi

  files=$(compose_files_all "$service")

  if [ -n "$profile" ]; then
    info "Stopping $service --profile $profile..."
    docker compose $files --profile "$profile" down
  else
    info "Stopping $service..."
    # always include all profiles on full down so nothing is left behind
    docker compose $files --profile ml down 2>/dev/null || docker compose $files down
  fi

  success "$service stopped"
}

do_logs() {
  service=$1
  env=$2
  dir="$BASE_DIR/$service"

  if [ ! -d "$dir" ]; then
    error "Service '$service' not found"
    return 1
  fi

  files=$(compose_files "$service" "$env")
  docker compose $files logs -f
}

show_help() {
  printf "\n"
  printf "${BOLD}  homeserver.sh — manage homeserver Docker services${RESET}\n"
  printf "\n"
  printf "  ${BOLD}Usage:${RESET}\n"
  printf "    ./homeserver.sh <env> <up|down|logs> <service|all> [service2 ...] [--profile <name>]\n"
  printf "\n"
  printf "  ${BOLD}Environments:${RESET}\n"
  printf "    dev    ports on all interfaces (direct access)\n"
  printf "    prod   ports on 127.0.0.1 only (nginx proxy handles external)\n"
  printf "\n"
  printf "  ${BOLD}Examples:${RESET}\n"
  printf "    ./homeserver.sh dev up all                      start all (dev)\n"
  printf "    ./homeserver.sh prod up all                     start all (prod)\n"
  printf "    ./homeserver.sh dev up landing mealie           start specific services\n"
  printf "    ./homeserver.sh prod up nextcloud immich        start multiple\n"
  printf "    ./homeserver.sh dev down all                    stop all\n"
  printf "    ./homeserver.sh dev down landing mealie         stop specific\n"
  printf "    ./homeserver.sh dev up immich --profile ml      add ML to running immich\n"
  printf "    ./homeserver.sh dev down immich --profile ml    remove only ML\n"
  printf "    ./homeserver.sh dev down immich                 stop immich + ML\n"
  printf "    ./homeserver.sh dev logs immich                 follow logs\n"
  printf "\n"
  printf "  ${BOLD}Services:${RESET}\n"
  printf "    %s\n" "$ALL_SERVICES" | fold -s -w 60 | sed 's/^/    /'
  printf "\n"
}

# ── Parse arguments ───────────────────────────────────────────────

if [ $# -lt 3 ]; then
  show_help
  exit 1
fi

ENV="$1"
ACTION="$2"
shift 2

# validate env
case "$ENV" in
  dev|prod) ;;
  help|--help|-h) show_help; exit 0 ;;
  *)
    error "Unknown env '$ENV' — use dev or prod"
    show_help
    exit 1
    ;;
esac

# validate action
case "$ACTION" in
  up|down|logs) ;;
  *)
    error "Unknown action '$ACTION' — use up, down, or logs"
    show_help
    exit 1
    ;;
esac

# collect services and optional --profile from remaining args
SERVICES_TO_RUN=""
PROFILE=""

while [ $# -gt 0 ]; do
  case "$1" in
    --profile)
      shift
      if [ -z "$1" ]; then
        error "--profile requires a name (e.g. --profile ml)"
        exit 1
      fi
      PROFILE="$1"
      ;;
    all)
      SERVICES_TO_RUN="$ALL_SERVICES"
      ;;
    *)
      if is_valid_service "$1"; then
        SERVICES_TO_RUN="$SERVICES_TO_RUN $1"
      else
        error "Unknown service '$1'"
        show_help
        exit 1
      fi
      ;;
  esac
  shift
done

if [ -z "$SERVICES_TO_RUN" ]; then
  error "No services specified"
  show_help
  exit 1
fi

# ── Execute ───────────────────────────────────────────────────────

case "$ACTION" in
  up)
    header "Starting services in $ENV mode..."
    for service in $SERVICES_TO_RUN; do
      do_up "$service" "$ENV" "$PROFILE"
    done
    printf "\n"
    success "Done"
    ;;
  down)
    header "Stopping services..."
    for service in $SERVICES_TO_RUN; do
      do_down "$service" "$ENV" "$PROFILE"
    done
    printf "\n"
    success "Done"
    ;;
  logs)
    # logs only makes sense for one service
    service=$(echo "$SERVICES_TO_RUN" | awk '{print $1}')
    do_logs "$service" "$ENV"
    ;;
esac
