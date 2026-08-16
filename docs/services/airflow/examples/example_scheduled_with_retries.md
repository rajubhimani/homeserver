# example_scheduled_with_retries

[← Airflow](../airflow.md) | [Home](../../../../setup.md)

---

A daily-scheduled DAG (`schedule="@daily"`, runs on its own, no manual trigger needed) with `retries`/`retry_delay`/backoff configured — the two things almost every real production DAG needs.

📍 `services/airflow/dags-examples/example_scheduled_with_retries.py:18`

```mermaid
flowchart LR
    call_flaky_api -->|fails, up to 3 retries<br/>exponential backoff| call_flaky_api
    call_flaky_api -->|succeeds| Done((success))
```

## Try it

Runs on its own daily — to see it now:

```bash
docker exec airflow-scheduler airflow dags unpause example_scheduled_with_retries
docker exec airflow-scheduler airflow dags trigger example_scheduled_with_retries
docker exec airflow-scheduler airflow dags list-runs example_scheduled_with_retries
```

---

[← Airflow](../airflow.md) | [Home](../../../../setup.md)
