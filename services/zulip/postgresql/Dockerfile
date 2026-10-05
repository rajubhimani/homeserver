# Zulip's own PostgreSQL image (zulip/zulip-postgresql), rebuilt on PostgreSQL 18.
#
# Upstream publishes zulip/zulip-postgresql only up to :14 (EOL 2026-11-12),
# while Zulip Server 12.x supports PostgreSQL 14-18 and says Docker installs
# upgrade PostgreSQL "via image bumps". This is upstream's Dockerfile-postgresql
# (zulip/zulip, tag 12.3) unchanged except for the pinned build args and flat
# COPY paths; the three copied files are vendored verbatim from that tag.
# See docs/services/zulip.md "Version line".
ARG PGROONGA_VERSION=4.0.9
ARG POSTGRESQL_VERSION=18
FROM groonga/pgroonga:$PGROONGA_VERSION-alpine-$POSTGRESQL_VERSION-slim

# Install hunspell, Zulip stop words, and run Zulip database
# init.
RUN apk add -U --no-cache hunspell-en
RUN ln -sf /usr/share/hunspell/en_US.dic /usr/local/share/postgresql/tsearch_data/en_us.dict && ln -sf /usr/share/hunspell/en_US.aff /usr/local/share/postgresql/tsearch_data/en_us.affix
COPY zulip_english.stop /usr/local/share/postgresql/tsearch_data/zulip_english.stop
COPY create-db.sql /docker-entrypoint-initdb.d/zulip-create-db.sql
COPY create-pgroonga.sql /docker-entrypoint-initdb.d/zulip-create-pgroonga.sql
