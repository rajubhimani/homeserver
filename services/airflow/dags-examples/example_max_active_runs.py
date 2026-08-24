"""Starter example — `max_active_runs`: capping how many runs of *this DAG*
Airflow will execute concurrently. The scheduler's own default is 16, so
without this a slow task and a tight schedule can pile up overlapping runs
that all touch the same downstream resource at once (a DB table, an API
rate limit, a file being written). Set it to 1 to force strictly serial
execution — the next scheduled run waits for the previous one to finish
regardless of how long the task takes.

This DAG runs every minute (`schedule="* * * * *"` — Airflow has no
`@minute` preset, only `@hourly`/`@daily`/etc.) with a task that sleeps
90s — longer than its own schedule interval — so a second run is always
due before the first finishes. With max_active_runs=1, watch the Grid
view: the queued run sits in `queued` state instead of starting, and only
begins once the prior run completes. Compare with `example_backfill`
(default concurrency, so its 5 catchup runs execute in parallel, not
serially) to see the difference.

    docker exec airflow-scheduler airflow dags unpause example_max_active_runs
    docker exec airflow-scheduler airflow dags list-runs example_max_active_runs
"""

import time
from datetime import datetime

from airflow.sdk import dag, task


@dag(
    dag_id="example_max_active_runs",
    description="Starter example: max_active_runs=1 serializes overlapping scheduled runs",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule="* * * * *",
    catchup=False,
    max_active_runs=1,
    tags=["example"],
)
def example_max_active_runs():
    @task
    def slow_task() -> None:
        print("Starting a 90s task — longer than the every-minute schedule interval.")
        time.sleep(90)
        print("Done.")

    slow_task()


example_max_active_runs()
