#!/bin/sh
# homeserver.sh — manage all homeserver services
#
# Usage:
#   ./homeserver.sh <env> <up|down|logs|update> <service|all> [service2 ...] [--profile <name>]
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
SERVICE_DATA_ROOT="$BASE_DIR/service_data"

# Load global config from root .env if present
if [ -f "$BASE_DIR/.env" ]; then
  # shellcheck disable=SC1090
  . "$BASE_DIR/.env"
fi
DOMAIN="${DOMAIN:-yourdomain.com}"

# Startup order — sequential, infrastructure first, monitoring last
SERVICES_UP="dozzle cloudflared nginx landing nextcloud vaultwarden gitea forgejo gitlab immich jellyfin paperless stirling-pdf-lite mealie uptime-kuma"

# Shutdown order — reverse
SERVICES_DOWN="uptime-kuma mealie stirling-pdf stirling-pdf-lite paperless jellyfin immich gitlab forgejo gitea vaultwarden nextcloud landing nginx cloudflared dozzle"

# Core group — infrastructure-only subset
SERVICES_CORE="dozzle nginx landing nextcloud"

# Extra services — valid but not in default 'all' list (start manually)
SERVICES_EXTRA="stirling-pdf nginx-plain wg-easy headscale openvpn portainer dockge"

# Timeout in seconds to wait for a service to become healthy
HEALTH_TIMEOUT=180

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
  for s in $SERVICES_UP $SERVICES_EXTRA; do
    [ "$s" = "$1" ] && return 0
  done
  return 1
}

compose_files() {
  service=$1
  env=$2
  dir="$BASE_DIR/$service"
  base=$(base_file "$service")
  files="-f $dir/$base"
  [ -f "$dir/compose.${env}.yml" ] && files="$files -f $dir/compose.${env}.yml"
  echo "$files"
}

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

# Wait for a service to become healthy or running
# Returns 0 on success, 1 on failure/timeout
wait_healthy() {
  service=$1
  elapsed=0
  interval=5

  # get the main container name for this service
  container=$(docker ps -a --format "{{.Names}}" | grep "^${service}$" | head -1)
  if [ -z "$container" ]; then
    # try common naming patterns
    container=$(docker ps -a --format "{{.Names}}" | grep "^${service}-" | grep -v "db\|redis\|worker" | head -1)
  fi
  [ -z "$container" ] && container="$service"

  printf "  ${CYAN}waiting for %s to be ready..." "$service"

  while [ $elapsed -lt $HEALTH_TIMEOUT ]; do
    status=$(docker inspect --format='{{.State.Status}}' "$container" 2>/dev/null)
    health=$(docker inspect --format='{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}' "$container" 2>/dev/null)

    if [ "$health" = "healthy" ]; then
      printf " ready (${elapsed}s)${RESET}\n"
      return 0
    elif [ "$health" = "none" ] && [ "$status" = "running" ]; then
      printf " ready (${elapsed}s)${RESET}\n"
      return 0
    elif [ "$status" = "exited" ] || [ "$status" = "dead" ]; then
      printf " exited${RESET}\n"
      return 1
    elif [ "$status" = "created" ]; then
      printf " dependency failed${RESET}\n"
      return 1
    fi
    # unhealthy = keep waiting; some services temporarily fail checks during boot

    sleep $interval
    elapsed=$((elapsed + interval))
    printf "."
  done

  printf " timeout after ${HEALTH_TIMEOUT}s${RESET}\n"
  return 1
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
  data_root="$SERVICE_DATA_ROOT/$service"

  if [ -n "$profile" ]; then
    info "Starting $service ($env) --profile $profile..."
    DATA_ROOT="$data_root" DOMAIN="$DOMAIN" docker compose $files --profile "$profile" up -d
  else
    info "Starting $service ($env)..."
    DATA_ROOT="$data_root" DOMAIN="$DOMAIN" docker compose $files up -d
  fi
  compose_rc=$?

  if [ $compose_rc -ne 0 ]; then
    # Capture output only on failure to detect zombie docker-proxy port conflicts
    if [ -n "$profile" ]; then
      compose_err=$(DATA_ROOT="$data_root" DOMAIN="$DOMAIN" docker compose $files --profile "$profile" up -d 2>&1)
    else
      compose_err=$(DATA_ROOT="$data_root" DOMAIN="$DOMAIN" docker compose $files up -d 2>&1)
    fi
    port=$(printf "%s" "$compose_err" | grep -oE 'listen tcp [^:]+:([0-9]+)' | grep -oE '[0-9]+$' | head -1)
    if [ -n "$port" ]; then
      warn "Port $port in use — freeing zombie docker-proxy and retrying..."
      sudo fuser -k "${port}/tcp" 2>/dev/null
      sleep 1
      if [ -n "$profile" ]; then
        DATA_ROOT="$data_root" DOMAIN="$DOMAIN" docker compose $files --profile "$profile" up -d
      else
        DATA_ROOT="$data_root" DOMAIN="$DOMAIN" docker compose $files up -d
      fi
      compose_rc=$?
    fi
    [ $compose_rc -ne 0 ] && return 1
  fi

  wait_healthy "$service"
  return $?
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
  data_root="$SERVICE_DATA_ROOT/$service"

  if [ -n "$profile" ]; then
    info "Stopping $service --profile $profile..."
    DATA_ROOT="$data_root" DOMAIN="$DOMAIN" docker compose $files --profile "$profile" down
  else
    info "Stopping $service..."
    DATA_ROOT="$data_root" DOMAIN="$DOMAIN" docker compose $files --profile ml down 2>/dev/null || DATA_ROOT="$data_root" DOMAIN="$DOMAIN" docker compose $files down
  fi

  success "$service stopped"
}

do_update() {
  service=$1
  env=$2
  dir="$BASE_DIR/$service"

  if [ ! -d "$dir" ]; then
    error "Service '$service' not found"
    return 1
  fi

  files=$(compose_files "$service" "$env")
  data_root="$SERVICE_DATA_ROOT/$service"

  info "Pulling latest images for $service..."
  DATA_ROOT="$data_root" DOMAIN="$DOMAIN" docker compose $files pull
  pull_rc=$?
  [ $pull_rc -ne 0 ] && warn "Pull had issues for $service — continuing with recreate anyway"

  info "Recreating $service ($env)..."
  DATA_ROOT="$data_root" DOMAIN="$DOMAIN" docker compose $files up -d --force-recreate
  compose_rc=$?
  [ $compose_rc -ne 0 ] && return 1

  wait_healthy "$service"
  return $?
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
  DATA_ROOT="$SERVICE_DATA_ROOT/$service" DOMAIN="$DOMAIN" docker compose $files logs -f
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
  printf "    ./homeserver.sh dev up all                      start all sequentially (dev)\n"
  printf "    ./homeserver.sh prod up all                     start all sequentially (prod)\n"
  printf "    ./homeserver.sh dev up core                     start core only (dozzle nginx landing nextcloud)\n"
  printf "    ./homeserver.sh dev down core                   stop core (reverse order)\n"
  printf "    ./homeserver.sh dev up landing mealie           start specific services\n"
  printf "    ./homeserver.sh dev down all                    stop all (reverse order)\n"
  printf "    ./homeserver.sh dev down landing mealie         stop specific\n"
  printf "    ./homeserver.sh dev up immich --profile ml      add ML to running immich\n"
  printf "    ./homeserver.sh dev down immich --profile ml    remove only ML\n"
  printf "    ./homeserver.sh dev logs immich                 follow logs\n"
  printf "    ./homeserver.sh dev update all                  pull latest images and recreate all\n"
  printf "    ./homeserver.sh dev update running              pull and recreate only currently running services\n"
  printf "    ./homeserver.sh dev update jellyfin             pull and update a single service\n"
  printf "\n"
  printf "  ${BOLD}Startup order (all):${RESET}\n"
  printf "    %s\n" "$SERVICES_UP"
  printf "\n"
  printf "  ${BOLD}Manual-only services (not in all):${RESET}\n"
  printf "    %s\n" "$SERVICES_EXTRA"
  printf "\n"
  printf "  ${BOLD}Health timeout:${RESET} ${HEALTH_TIMEOUT}s per service\n"
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

case "$ENV" in
  dev|prod) ;;
  help|--help|-h) show_help; exit 0 ;;
  *)
    error "Unknown env '$ENV' — use dev or prod"
    show_help
    exit 1
    ;;
esac

case "$ACTION" in
  up|down|logs|update) ;;
  *)
    error "Unknown action '$ACTION' — use up, down, logs, or update"
    show_help
    exit 1
    ;;
esac

SERVICES_TO_RUN=""
PROFILE=""
RUN_ALL=0
RUN_CORE=0
RUN_RUNNING=0

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
      RUN_ALL=1
      ;;
    core)
      RUN_CORE=1
      ;;
    running)
      RUN_RUNNING=1
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

if [ $RUN_ALL -eq 0 ] && [ $RUN_CORE -eq 0 ] && [ $RUN_RUNNING -eq 0 ] && [ -z "$SERVICES_TO_RUN" ]; then
  error "No services specified"
  show_help
  exit 1
fi

# ── Helpers ───────────────────────────────────────────────────────

# Returns the subset of SERVICES_UP that have at least one running container,
# preserving startup order.
get_running_services() {
  running_containers=$(docker ps --format "{{.Names}}")
  result=""
  for svc in $SERVICES_UP $SERVICES_EXTRA; do
    if printf "%s" "$running_containers" | grep -qE "^${svc}(-|$)"; then
      result="$result $svc"
    fi
  done
  printf "%s" "$result"
}

# ── Pre-flight checks ─────────────────────────────────────────────

ensure_network() {
  if ! docker network inspect homeserver >/dev/null 2>&1; then
    warn "Docker network 'homeserver' not found — creating..."
    docker network create homeserver >/dev/null
    success "Network 'homeserver' created"
  fi
}

# ── Execute ───────────────────────────────────────────────────────

case "$ACTION" in
  up)
    ensure_network
    header "Starting services in $ENV mode..."

    # pick ordered list or custom list
    if [ $RUN_ALL -eq 1 ]; then
      list="$SERVICES_UP"
    elif [ $RUN_CORE -eq 1 ]; then
      list="$SERVICES_CORE"
    else
      list="$SERVICES_TO_RUN"
    fi

    FAILED=""
    for service in $list; do
      do_up "$service" "$ENV" "$PROFILE"
      if [ $? -ne 0 ]; then
        error "$service FAILED"
        FAILED="$FAILED $service"
      else
        success "$service started"
      fi
      printf "\n"
    done

    # summary
    printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
    if [ -z "$FAILED" ]; then
      success "All services started successfully"
    else
      warn "Completed with failures:"
      for f in $FAILED; do
        error "  $f"
      done
      printf "\n  Run ${CYAN}sh homeserver.sh $ENV logs <service>${RESET} to investigate\n"
    fi
    printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"
    ;;

  down)
    header "Stopping services..."

    if [ $RUN_ALL -eq 1 ]; then
      list="$SERVICES_DOWN"
    elif [ $RUN_CORE -eq 1 ]; then
      list="$(echo "$SERVICES_CORE" | tr ' ' '\n' | tac | tr '\n' ' ')"
    else
      list="$SERVICES_TO_RUN"
    fi

    for service in $list; do
      do_down "$service" "$ENV" "$PROFILE"
    done

    printf "\n"
    success "Done"
    ;;

  logs)
    service=$(echo "$SERVICES_TO_RUN" | awk '{print $1}')
    [ $RUN_ALL -eq 1 ] && service=$(echo "$SERVICES_UP" | awk '{print $1}')
    do_logs "$service" "$ENV"
    ;;

  update)
    ensure_network
    header "Updating services in $ENV mode..."

    if [ $RUN_ALL -eq 1 ]; then
      list="$SERVICES_UP"
    elif [ $RUN_CORE -eq 1 ]; then
      list="$SERVICES_CORE"
    elif [ $RUN_RUNNING -eq 1 ]; then
      list=$(get_running_services)
      if [ -z "$list" ]; then
        warn "No running services detected"
        exit 0
      fi
      info "Detected running services:$list"
      printf "\n"
    else
      list="$SERVICES_TO_RUN"
    fi

    FAILED=""
    for service in $list; do
      do_update "$service" "$ENV"
      if [ $? -ne 0 ]; then
        error "$service FAILED"
        FAILED="$FAILED $service"
      else
        success "$service updated"
      fi
      printf "\n"
    done

    printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
    if [ -z "$FAILED" ]; then
      success "All services updated successfully"
    else
      warn "Completed with failures:"
      for f in $FAILED; do
        error "  $f"
      done
      printf "\n  Run ${CYAN}sh homeserver.sh $ENV logs <service>${RESET} to investigate\n"
    fi
    printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"
    ;;
esac
