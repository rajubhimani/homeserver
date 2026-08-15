"""Starter example — fan-out/fan-in: multiple independent tasks running
concurrently, then downstream tasks that wait for all of them. Every other
multi-task example here is either a straight line (example_etl_pipeline) or
an either/or branch (example_branching) — this is the third real shape:
parallel work that converges. Also deliberately uses the classic Operator
style with explicit dependencies and `ti.xcom_pull`, not TaskFlow's `@task`
decorators — the two styles look different but produce the same kind of
DAG; compare against example_etl_pipeline.py to see both side by side.

Four levels, so upstream/downstream is unambiguous at every step:

    start                                     (level 0)
      -> fetch_source_a/b/c (parallel)        (level 1 — all downstream of start)
        -> combine_results                    (level 2 — downstream of all 3, upstream of notify)
          -> notify                            (level 3)

fetch_source_a/b/c have no dependency on *each other* (only on `start`), so
LocalExecutor runs them at the same time — watch the overlap in the UI's
Gantt view, or `docker exec airflow-scheduler airflow tasks states-for-dag-run
example_parallel_tasks <run_id>` mid-run. `combine_results` only starts once
all three have finished (Airflow won't run a task until every one of its
upstream tasks succeeds); `notify` only starts once `combine_results` has.

Two equivalent ways to declare the same dependency — `>>` is shorthand for
`.set_downstream()` (and `<<` for `.set_upstream()`); every other example in
this repo uses `>>`, this one also shows the explicit method form once so
both are visible somewhere:

    start >> fetch_source_a                    # shorthand
    start.set_downstream(fetch_source_a)        # equivalent, explicit
    fetch_source_a.set_upstream(start)           # same edge, written from the other end
"""

from datetime import datetime

from airflow import DAG
from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.standard.operators.python import PythonOperator


def fetch_source(source_name: str):
    def _fetch(ti=None):
        # Real version: call that source's actual API/DB.
        value = {"source_a": 10, "source_b": 20, "source_c": 30}[source_name]
        print(f"Fetched {value} from {source_name}")
        ti.xcom_push(key="value", value=value)

    return _fetch


def combine_results(ti=None, **_) -> None:
    values = ti.xcom_pull(task_ids=["fetch_source_a", "fetch_source_b", "fetch_source_c"], key="value")
    print(f"Combined total from all 3 sources: {sum(values)}")


def notify(ti=None, **_) -> None:
    # Real version: post to ntfy, Slack, etc. ti.xcom_pull with no `key`
    # fetches the default return-value XCom — combine_results didn't
    # explicitly push one, but Airflow auto-XComs a task's `return` value.
    print(f"Pipeline finished. Its upstream task ({ti.task.upstream_task_ids}) already confirmed success.")


with DAG(
    dag_id="example_parallel_tasks",
    description="Starter example: fan-out to parallel tasks, fan-in to one that waits for all of them",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
) as dag:
    start = EmptyOperator(task_id="start")

    fetch_source_a = PythonOperator(task_id="fetch_source_a", python_callable=fetch_source("source_a"))
    fetch_source_b = PythonOperator(task_id="fetch_source_b", python_callable=fetch_source("source_b"))
    fetch_source_c = PythonOperator(task_id="fetch_source_c", python_callable=fetch_source("source_c"))

    combine = PythonOperator(task_id="combine_results", python_callable=combine_results)
    notify_task = PythonOperator(task_id="notify", python_callable=notify)

    # Shorthand form for the fan-out/fan-in (this is what every other
    # example in this repo uses):
    start >> [fetch_source_a, fetch_source_b, fetch_source_c] >> combine

    # Explicit method form for the last edge — same effect as
    # `combine >> notify_task`, written the other two ways:
    combine.set_downstream(notify_task)
    # notify_task.set_upstream(combine)   # <- the same edge again, from the downstream side (would be redundant to actually call both)
