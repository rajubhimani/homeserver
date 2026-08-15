#!/bin/bash
# Bootstraps 3 separate databases (one per test app) inside a single shared
# Postgres instance — the actual thing this experiment is testing. Runs as
# the superuser ($POSTGRES_USER, set to "postgres" — see .env.example),
# connecting explicitly to each target database rather than relying on the
# entrypoint's default POSTGRES_DB targeting, since that only ever
# initializes the ONE database named by POSTGRES_DB.
set -e

create_db_and_user() {
  local db="$1"
  local user="$2"
  local password="$3"

  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname postgres <<-EOSQL
      CREATE USER "$user" WITH PASSWORD '$password';
      CREATE DATABASE "$db" OWNER "$user";
EOSQL

  psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$db" <<-EOSQL
      GRANT ALL ON SCHEMA public TO "$user";
      ALTER SCHEMA public OWNER TO "$user";
EOSQL
}

create_db_and_user "$FIREFLY_TEST_DB" "$FIREFLY_TEST_USER" "$FIREFLY_TEST_PASSWORD"
create_db_and_user "$FORGEJO_TEST_DB" "$FORGEJO_TEST_USER" "$FORGEJO_TEST_PASSWORD"
create_db_and_user "$GUACAMOLE_TEST_DB" "$GUACAMOLE_TEST_USER" "$GUACAMOLE_TEST_PASSWORD"

# Guacamole needs its schema pre-loaded (it has no self-migration on first
# boot the way firefly/forgejo do) — load it into guacamole_test specifically,
# as the guacamole_test role so it owns every object it creates.
psql -v ON_ERROR_STOP=1 --username "$GUACAMOLE_TEST_USER" --dbname "$GUACAMOLE_TEST_DB" \
  -f /docker-entrypoint-initdb.d/guacamole/schema.sql

echo "shared-postgres experiment: 3 databases + guacamole schema created"
