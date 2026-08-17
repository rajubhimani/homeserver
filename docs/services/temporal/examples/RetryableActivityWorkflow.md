# RetryableActivityWorkflow

[← Temporal](../temporal.md) | [Home](../../../../setup.md)

---

Durability. `flaky_activity` fails on its first two calls and succeeds on the third; the Workflow code has zero retry logic written — Temporal's `RetryPolicy` handles it. The same "fails twice, succeeds on the third attempt" shape as Airflow's [`example_scheduled_with_retries`](../../airflow/examples/example_scheduled_with_retries.md) and Dagster's [`flaky_retry_asset`](../../dagster/examples/flaky_retry_asset.md) — see the [feature-parity table](../../../12-orchestration.md) for all three side by side.

**Real-world problem:** an external API call fails intermittently — a network blip, a momentary 500 — that has nothing to do with your code being wrong. Without built-in retries, every one of those transient hiccups becomes a permanent failure that pages someone at 3am for a problem that would have resolved itself on the next attempt.

📍 `services/temporal/worker/workflows.py:42` (workflow) / `services/temporal/worker/activities.py:46` (`flaky_activity`)

```mermaid
sequenceDiagram
    participant W as RetryableActivityWorkflow
    participant A as flaky_activity
    W->>A: attempt 1
    A-->>W: RuntimeError
    Note over W: RetryPolicy backoff
    W->>A: attempt 2
    A-->>W: RuntimeError
    Note over W: RetryPolicy backoff
    W->>A: attempt 3
    A-->>W: success
```

Watch it retry live: start it, then open the workflow in the UI and look at its Event History (`ActivityTaskStarted`/`ActivityTaskFailed` pairs before the final success).

## Try it

```bash
docker exec -it temporal-admin-tools temporal workflow start --address temporal:7233 \
  --task-queue homeserver \
  --type RetryableActivityWorkflow \
  --input '"demo-1"'
```

---

[← Temporal](../temporal.md) | [Home](../../../../setup.md)
