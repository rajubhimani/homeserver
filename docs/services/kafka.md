# Kafka

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** An event-streaming broker for your own projects: durable, replayable logs with many independent consumers. Not a web app: no landing card, no public hostname.
**Port:** `9092` (host) → `9092` (container) | **Data:** named volume `kafka-data` | **Tier:** extra | **Requires:** nothing (KRaft, no ZooKeeper)

## When to use it (and when not)

- Job queues: use RabbitMQ or the shared [Valkey](valkey.md).
- Durable multi-step workflows: use [Temporal](temporal/temporal.md).
- Event streams that several consumers read independently, replay, or keep for days: this.

## What runs

One container, `apache/kafka:4.4.0` (Apache's official image), a single node that is both broker and controller (KRaft combined mode). Kafka has no LTS track, so this is the newest supported release. Environment layout follows upstream's `docker/examples/docker-compose-files/single-node/plaintext`. Single node means replication factor 1 for the internal topics; there is no fault tolerance.

## Setup

```bash
cp services/kafka/.env.example services/kafka/.env
chmod 600 services/kafka/.env
uv run homeserver.py dev up kafka
```

Generate your own `KAFKA_CLUSTER_ID` before the first start (command in `.env.example`) and never change it afterwards: against existing data the broker refuses to start.

## Connecting

Two listeners, because Kafka tells clients which address to use for every later request:

| From | Bootstrap server | Listener |
| --- | --- | --- |
| Another container on the `homeserver` network | `kafka:19092` | `INTERNAL` |
| This machine | `localhost:9092` | `EXTERNAL` |
| Other devices (LAN / WireGuard) | `<server-ip>:9092` | `EXTERNAL`, set `KAFKA_EXTERNAL_HOST` to that IP |

Apps take the endpoint from their own `.env` (`MQ_HOST=kafka`, `MQ_PORT=19092`), never hardcoded.

Try it:

```bash
docker exec kafka /opt/kafka/bin/kafka-topics.sh --bootstrap-server localhost:19092 --create --topic test
echo hello | docker exec -i kafka /opt/kafka/bin/kafka-console-producer.sh --bootstrap-server localhost:19092 --topic test
docker exec kafka /opt/kafka/bin/kafka-console-consumer.sh --bootstrap-server localhost:19092 --topic test --from-beginning --max-messages 1
```

## Configuration

| Variable | Default | Meaning |
| --- | --- | --- |
| `KAFKA_CLUSTER_ID` | example UUID | KRaft cluster ID; generate once, keep forever |
| `KAFKA_EXTERNAL_HOST` | `localhost` | Address advertised to clients outside Docker |
| `KAFKA_AUTO_CREATE_TOPICS_ENABLE` | `true` | Create topics on first produce |
| `KAFKA_LOG_RETENTION_HOURS` | `168` | Message retention (7 days) |
| `KAFKA_HEAP_OPTS` | `-Xmx512M -Xms512M` | JVM heap |

## Notes

- Plaintext, no authentication: the ports are reachable only from the host (and WireGuard in prod) and never opened on the router. Do not publish `9092` beyond that. Add SASL if you ever need to.
- No web UI is included. A browser UI such as `kafka-ui` can be added later if wanted.
- Data lives in a named volume, so the `down` auto-snapshot does not archive it.

## Memory limits

`compose.yml` caps these containers with `deploy.resources.limits.memory` (added 2026-11-08): `kafka` 1G. Limits are sized from measured idle with headroom, or upstream's documented minimum where one exists; a backstop against one container exhausting host RAM — raise it if `docker inspect <name> --format '{{.State.OOMKilled}}'` shows true.
