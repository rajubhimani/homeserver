#!/bin/sh
# homeserver.sh — manage all homeserver services
#
# Usage:
#   ./homeserver.sh <env> <up|down|restart|logs|update> <min|core|all|running|service...> [--profile <name>]
#   ./homeserver.sh <env> -r <service...>  (shorthand for restart)
#
# Service tiers:
#   min  — bare minimum to run the server (dozzle, nginx-plain, landing)
#   core — full default stack, includes min (starts with 'up core' or 'up all')
#   all  — core + extra (everything); down all always stops everything
#   extra — optional/manual services, not started by 'up core'
#
# IMPORTANT: When adding a new service —
#   - Add to SERVICES_CORE if it should auto-start with 'up core'
#   - Add to SERVICES_EXTRA if it is optional/manual
#   - That is all — 'up all' and 'down all' derive everything automatically

BASE_DIR="$(cd "$(dirname "$0")" && pwd)"
SERVICE_DATA_ROOT="$BASE_DIR/service_data"

# Load global config from root .env if present
if [ -f "$BASE_DIR/.env" ]; then
  # shellcheck disable=SC1090
  . "$BASE_DIR/.env"
fi
DOMAIN="${DOMAIN:-yourdomain.com}"

# ── Service tiers ─────────────────────────────────────────────────
# MIN ⊂ CORE ⊂ ALL (ALL = CORE + EXTRA)

# ── Service tiers (additive: each tier builds on the previous) ────
#
#   up min  = MIN
#   up core = MIN + CORE
#   up all  = MIN + CORE + EXTRA
#
#   down min/core/all = same sets, reversed
#
# NEW SERVICES ALWAYS GO INTO SERVICES_EXTRA FIRST.
# Move to SERVICES_CORE only when explicitly asked to.

# Infrastructure — reverse proxy, tunnel, log viewer, landing page
SERVICES_MIN="dozzle cloudflared nginx-plain landing"

# Always-on apps added on top of MIN (currently just nextcloud)
SERVICES_CORE="nextcloud"

# Everything else — started with 'up all' or individually
SERVICES_EXTRA="vaultwarden gitea forgejo gitlab immich jellyfin paperless stirling-pdf-lite mealie uptime-kuma stirling-pdf nginx stalwart snappymail roundcube syncthing authentik ntfy miniflux audiobookshelf conduit openproject plane crater wg-easy headscale openvpn portainer dockge"

# Timeout in seconds to wait for a service to become healthy
HEALTH_TIMEOUT=180

# ── Colors ────────────────────────────────────────────────────────
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

# ── Helpers ───────────────────────────────────────────────────────

# Reverse a space-separated list
reverse_list() {
  printf "%s" "$1" | tr ' ' '\n' | awk 'NF{a[++n]=$0} END{for(i=n;i>=1;i--)printf "%s ",a[i]}' | sed 's/ $//'
}

base_file() {
  [ "$1" = "landing" ] && echo "docker-compose.yml" || echo "compose.yml"
}

is_valid_service() {
  for s in $SERVICES_MIN $SERVICES_CORE $SERVICES_EXTRA; do
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

# Returns currently running services across all tiers, preserving startup order
get_running_services() {
  running_containers=$(docker ps --format "{{.Names}}")
  result=""
  for svc in $SERVICES_MIN $SERVICES_CORE $SERVICES_EXTRA; do
    if printf "%s" "$running_containers" | grep -qE "^${svc}(-|$)"; then
      result="$result $svc"
    fi
  done
  printf "%s" "$result"
}

# ── Wait for healthy ──────────────────────────────────────────────

wait_healthy() {
  service=$1
  elapsed=0
  interval=5

  container=$(docker ps -a --format "{{.Names}}" | grep "^${service}$" | head -1)
  if [ -z "$container" ]; then
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

    sleep $interval
    elapsed=$((elapsed + interval))
    printf "."
  done

  printf " timeout after ${HEALTH_TIMEOUT}s${RESET}\n"
  return 1
}

# ── Actions ───────────────────────────────────────────────────────

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

do_restart() {
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
    info "Restarting $service ($env) --profile $profile..."
    DATA_ROOT="$data_root" DOMAIN="$DOMAIN" docker compose $files --profile "$profile" up -d --force-recreate
  else
    info "Restarting $service ($env)..."
    DATA_ROOT="$data_root" DOMAIN="$DOMAIN" docker compose $files up -d --force-recreate
  fi
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

# ── Help ──────────────────────────────────────────────────────────

show_help() {
  printf "\n"
  printf "${BOLD}  homeserver.sh — manage homeserver Docker services${RESET}\n"
  printf "\n"
  printf "  ${BOLD}Usage:${RESET}\n"
  printf "    ./homeserver.sh <env> <up|down|restart|logs|update> <tier|service...> [--profile <name>]\n"
  printf "    ./homeserver.sh <env> -u <service...>                     (up shorthand)\n"
  printf "    ./homeserver.sh <env> -d <service...>                     (down shorthand)\n"
  printf "    ./homeserver.sh <env> -r <service...>                     (restart shorthand)\n"
  printf "\n"
  printf "  ${BOLD}Environments:${RESET}\n"
  printf "    dev    ports on all interfaces (direct access)\n"
  printf "    prod   ports on 127.0.0.1 only (nginx proxy handles external)\n"
  printf "\n"
  printf "  ${BOLD}Tiers:${RESET}\n"
  printf "    min     bare minimum — dozzle, nginx-plain, landing\n"
  printf "    core    full default stack (includes min)\n"
  printf "    all     core + extra — starts/stops everything\n"
  printf "    running update only — currently running services\n"
  printf "\n"
  printf "  ${BOLD}Examples:${RESET}\n"
  printf "    ./homeserver.sh dev up min                      start bare minimum\n"
  printf "    ./homeserver.sh dev up core                     start full default stack\n"
  printf "    ./homeserver.sh dev up all                      start everything (core + extra)\n"
  printf "    ./homeserver.sh dev down min                    stop minimum (reverse order)\n"
  printf "    ./homeserver.sh dev down core                   stop core (reverse order)\n"
  printf "    ./homeserver.sh dev down all                    stop everything (reverse order)\n"
  printf "    ./homeserver.sh dev up landing mealie           start specific services\n"
  printf "    ./homeserver.sh dev down landing mealie         stop specific services\n"
  printf "    ./homeserver.sh dev up immich --profile ml      add ML profile to immich\n"
  printf "    ./homeserver.sh dev down immich --profile ml    remove ML profile\n"
  printf "    ./homeserver.sh dev restart nginx-plain          restart a service (re-runs entrypoint)
    ./homeserver.sh dev -r nginx-plain              same, shorthand
    ./homeserver.sh dev logs immich                 follow logs\n"
  printf "    ./homeserver.sh dev update all                  pull latest and recreate all\n"
  printf "    ./homeserver.sh dev update running              update only currently running\n"
  printf "    ./homeserver.sh dev update jellyfin             update a single service\n"
  printf "\n"
  printf "  ${BOLD}MIN (infrastructure):${RESET}\n"
  printf "    %s\n" "$SERVICES_MIN"
  printf "\n"
  printf "  ${BOLD}CORE (always-on apps, added on top of min):${RESET}\n"
  printf "    %s\n" "$SERVICES_CORE"
  printf "\n"
  printf "  ${BOLD}EXTRA (optional, started with 'up all' or individually):${RESET}\n"
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
  up|-u|down|-d|restart|-r|logs|update) ;;
  *)
    error "Unknown action '$ACTION' — use up, down, restart, logs, or update"
    show_help
    exit 1
    ;;
esac

SERVICES_TO_RUN=""
PROFILE=""
RUN_ALL=0
RUN_CORE=0
RUN_MIN=0
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
    all)     RUN_ALL=1 ;;
    core)    RUN_CORE=1 ;;
    min)     RUN_MIN=1 ;;
    running) RUN_RUNNING=1 ;;
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

if [ $RUN_ALL -eq 0 ] && [ $RUN_CORE -eq 0 ] && [ $RUN_MIN -eq 0 ] && [ $RUN_RUNNING -eq 0 ] && [ -z "$SERVICES_TO_RUN" ]; then
  error "No services specified"
  show_help
  exit 1
fi

# ── Pre-flight ────────────────────────────────────────────────────

ensure_network() {
  if ! docker network inspect homeserver >/dev/null 2>&1; then
    warn "Docker network 'homeserver' not found — creating..."
    docker network create homeserver >/dev/null
    success "Network 'homeserver' created"
  fi
}

# ── Execute ───────────────────────────────────────────────────────

run_list() {
  action_fn=$1
  list=$2
  env=$3
  profile=$4
  label=$5

  FAILED=""
  for service in $list; do
    $action_fn "$service" "$env" "$profile"
    if [ $? -ne 0 ]; then
      error "$service FAILED"
      FAILED="$FAILED $service"
    else
      [ "$action_fn" = "do_up" ] && success "$service started"
      [ "$action_fn" = "do_update" ] && success "$service updated"
    fi
    printf "\n"
  done

  printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n"
  if [ -z "$FAILED" ]; then
    success "$label completed successfully"
  else
    warn "Completed with failures:"
    for f in $FAILED; do error "  $f"; done
    printf "\n  Run ${CYAN}sh homeserver.sh $ENV logs <service>${RESET} to investigate\n"
  fi
  printf "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${RESET}\n\n"
}

case "$ACTION" in
  up|-u)
    ensure_network
    if [ $RUN_ALL -eq 1 ]; then
      header "Starting all services (min + core + extra) in $ENV mode..."
      run_list do_up "$SERVICES_MIN $SERVICES_CORE $SERVICES_EXTRA" "$ENV" "$PROFILE" "All services"
    elif [ $RUN_CORE -eq 1 ]; then
      header "Starting core services (min + core) in $ENV mode..."
      run_list do_up "$SERVICES_MIN $SERVICES_CORE" "$ENV" "$PROFILE" "Core services"
    elif [ $RUN_MIN -eq 1 ]; then
      header "Starting min services in $ENV mode..."
      run_list do_up "$SERVICES_MIN" "$ENV" "$PROFILE" "Min services"
    else
      header "Starting services in $ENV mode..."
      run_list do_up "$SERVICES_TO_RUN" "$ENV" "$PROFILE" "Services"
    fi
    ;;

  down|-d)
    if [ $RUN_ALL -eq 1 ]; then
      header "Stopping all services (reverse order)..."
      list=$(reverse_list "$SERVICES_MIN $SERVICES_CORE $SERVICES_EXTRA")
      for service in $list; do do_down "$service" "$ENV" "$PROFILE"; done
    elif [ $RUN_CORE -eq 1 ]; then
      header "Stopping core services (reverse order)..."
      list=$(reverse_list "$SERVICES_MIN $SERVICES_CORE")
      for service in $list; do do_down "$service" "$ENV" "$PROFILE"; done
    elif [ $RUN_MIN -eq 1 ]; then
      header "Stopping min services (reverse order)..."
      list=$(reverse_list "$SERVICES_MIN")
      for service in $list; do do_down "$service" "$ENV" "$PROFILE"; done
    else
      header "Stopping services..."
      for service in $SERVICES_TO_RUN; do do_down "$service" "$ENV" "$PROFILE"; done
    fi
    printf "\n"
    success "Done"
    ;;

  restart|-r)
    ensure_network
    if [ $RUN_ALL -eq 1 ]; then
      header "Restarting all services in $ENV mode..."
      run_list do_restart "$SERVICES_MIN $SERVICES_CORE $SERVICES_EXTRA" "$ENV" "$PROFILE" "All services"
    elif [ $RUN_CORE -eq 1 ]; then
      header "Restarting core services in $ENV mode..."
      run_list do_restart "$SERVICES_MIN $SERVICES_CORE" "$ENV" "$PROFILE" "Core services"
    elif [ $RUN_MIN -eq 1 ]; then
      header "Restarting min services in $ENV mode..."
      run_list do_restart "$SERVICES_MIN" "$ENV" "$PROFILE" "Min services"
    else
      header "Restarting services in $ENV mode..."
      run_list do_restart "$SERVICES_TO_RUN" "$ENV" "$PROFILE" "Services"
    fi
    ;;

  logs)
    service=$(echo "$SERVICES_TO_RUN" | awk '{print $1}')
    [ $RUN_ALL -eq 1 ] && service=$(echo "$SERVICES_MIN" | awk '{print $1}')
    do_logs "$service" "$ENV"
    ;;

  update)
    ensure_network
    if [ $RUN_ALL -eq 1 ]; then
      header "Updating all services (min + core + extra) in $ENV mode..."
      run_list do_update "$SERVICES_MIN $SERVICES_CORE $SERVICES_EXTRA" "$ENV" "$PROFILE" "All services"
    elif [ $RUN_CORE -eq 1 ]; then
      header "Updating core services (min + core) in $ENV mode..."
      run_list do_update "$SERVICES_MIN $SERVICES_CORE" "$ENV" "$PROFILE" "Core services"
    elif [ $RUN_MIN -eq 1 ]; then
      header "Updating min services in $ENV mode..."
      run_list do_update "$SERVICES_MIN" "$ENV" "$PROFILE" "Min services"
    elif [ $RUN_RUNNING -eq 1 ]; then
      header "Updating running services in $ENV mode..."
      list=$(get_running_services)
      if [ -z "$list" ]; then
        warn "No running services detected"
        exit 0
      fi
      info "Detected running services:$list"
      printf "\n"
      run_list do_update "$list" "$ENV" "$PROFILE" "Running services"
    else
      header "Updating services in $ENV mode..."
      run_list do_update "$SERVICES_TO_RUN" "$ENV" "$PROFILE" "Services"
    fi
    ;;
esac
