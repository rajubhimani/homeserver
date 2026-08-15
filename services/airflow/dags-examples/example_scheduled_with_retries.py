"""Starter example — a daily-scheduled DAG with retry/backoff configured,
the two things almost every real production DAG needs: run on its own
without manual triggering, and not fail outright on the first transient
error (a flaky API, a momentary network blip, etc.)."""

from datetime import datetime, timedelta

from airflow import DAG
from airflow.providers.standard.operators.python import PythonOperator


def call_flaky_api() -> None:
    # Real version: an actual HTTP call. This DAG exists to show the retry
    # *configuration* below, not to simulate failure — it just succeeds.
    print("Called the API successfully.")


with DAG(
    dag_id="example_scheduled_with_retries",
    description="Starter example: daily schedule + per-task retry/backoff",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule="@daily",
    catchup=False,
    tags=["example"],
    default_args={
        "retries": 3,
        "retry_delay": timedelta(minutes=5),
        "retry_exponential_backoff": True,
        "max_retry_delay": timedelta(minutes=30),
    },
) as dag:
    PythonOperator(
        task_id="call_flaky_api",
        python_callable=call_flaky_api,
    )
