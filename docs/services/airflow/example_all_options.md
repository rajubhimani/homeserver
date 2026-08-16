# example_all_options

[← Airflow](airflow.md) | [Home](../../../setup.md)

---

Reference, not a pattern demo: every `@dag`/`@task` option in one file, each shown at its real default with a one-line explanation (a handful set for real, everything else commented-out as a checklist to copy from). Captured against Airflow 3.3.1 via `inspect.signature()` against `DAG.__init__`/`BaseOperator.__init__` — the source of truth if this ever drifts.

📍 `services/airflow/dags-examples/example_all_options.py:27` (`@dag(...)`) / `:62` (`@task(...)`)

```mermaid
flowchart LR
    reference_task
```

**Verified:** parses with no import errors and runs to `success` end to end.

## Try it

```bash
docker exec airflow-scheduler airflow dags unpause example_all_options
docker exec airflow-scheduler airflow dags trigger example_all_options
docker exec airflow-scheduler airflow dags list-runs example_all_options
```

---

[← Airflow](airflow.md) | [Home](../../../setup.md)
