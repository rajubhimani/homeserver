# example_hello_world

[← Airflow](../airflow.md) | [Home](../../../../setup.md)

---

A single task, nothing else. Start here if you've never used Airflow before.

**Real-world problem:** before wiring up anything real, you need to know the smallest amount of code required to get a DAG actually showing up and running — without that confirmed working first, debugging a more complex pipeline later is guesswork about whether the problem is your setup or your logic.

📍 `services/airflow/dags-examples/example_hello_world.py:20`

```mermaid
flowchart LR
    hello
```

## Try it

```bash
docker exec airflow-scheduler airflow dags unpause example_hello_world
docker exec airflow-scheduler airflow dags trigger example_hello_world
docker exec airflow-scheduler airflow dags list-runs example_hello_world
```

---

[← Airflow](../airflow.md) | [Home](../../../../setup.md)
