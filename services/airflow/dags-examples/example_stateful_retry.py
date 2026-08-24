"""Starter example — the Task State Store (AIP-103, new in Airflow 3.3): a
task can persist key-value state that survives across *retries*, not just
within a single successful run. XCom (used throughout `example_etl_pipeline`
and others) passes data between different *tasks* in the same run;
task_state_store solves a different problem — a single task's own memory of
what it already did, kept even when that specific attempt fails and Airflow
retries it. A plain Python variable inside the task function is wiped out on
every retry attempt; task_state_store isn't.

The canonical real use: submitting a long-running external job (a Spark job,
an export, an ML training run) and reattaching to it on retry instead of
submitting a duplicate.

This task's first attempt always "crashes" right after submitting a
(simulated) job, forcing a real retry. Watch the log change from "submitted
job: <id>" (try 1) to "reattaching to existing job: <id>" (try 2) — same
job_id both times. Verified: both attempts logged the identical job_id, and
the run ultimately succeeds on try 2.

    docker exec airflow-scheduler airflow dags unpause example_stateful_retry
    docker exec airflow-scheduler airflow dags trigger example_stateful_retry

The UI's task instance view has a **Storage** tab that shows the raw
task_state_store contents directly — a good place to watch this live.
"""

from __future__ import annotations

import random
import string
import time
from datetime import datetime, timedelta, timezone

from airflow.sdk import DAG, task
from airflow.sdk.execution_time.context import NEVER_EXPIRE


def _submit_job() -> str:
    # Real version: call the external system's submit API.
    time.sleep(1)
    return "job-" + "".join(random.choices(string.ascii_lowercase + string.digits, k=8))


def _poll_job(job_id: str) -> dict:
    # Real version: poll the external system's status API.
    time.sleep(1)
    return {"job_id": job_id, "status": "succeeded", "rows_written": random.randint(100, 10_000)}


with DAG(
    dag_id="example_stateful_retry",
    description="Starter example: task_state_store survives retries, unlike a plain local variable",
    doc_md=__doc__,
    schedule=None,
    start_date=datetime(2026, 1, 1),
    catchup=False,
    tags=["example"],
):

    @task(retries=2, retry_delay=timedelta(seconds=5))
    def run_job(task_state_store=None, ti=None):
        job_id = task_state_store.get("job_id")
        if job_id:
            print(f"Try {ti.try_number}: reattaching to existing job: {job_id}")
        else:
            job_id = _submit_job()
            # NEVER_EXPIRE so the job ID survives across every retry attempt,
            # not just until some default TTL.
            task_state_store.set("job_id", job_id, retention=NEVER_EXPIRE)
            task_state_store.set("submitted_at", datetime.now(tz=timezone.utc).isoformat())
            print(f"Try {ti.try_number}: submitted job: {job_id}")

            # Simulate a worker crash right after submission on the first
            # attempt — the retry reattaches to this same job_id instead of
            # submitting a duplicate.
            raise RuntimeError(f"Simulated failure after submitting {job_id} — retry will reattach")

        task_state_store.set("status", "running")
        result = _poll_job(job_id)
        task_state_store.set("status", "complete")
        task_state_store.set("result", result)

        print(f"Try {ti.try_number}: job complete — {result['rows_written']} rows written")
        return result["rows_written"]

    run_job()
