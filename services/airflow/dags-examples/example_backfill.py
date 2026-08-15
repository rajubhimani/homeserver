"""Starter example — Airflow's answer to "process historical dates":
catchup + backfill. This is whole-DAG-run granularity (one run per missed
schedule interval), not per-asset-partition like Dagster's daily_sales
(see docs/12-orchestration.md for the real distinction).

start_date is 5 days in the past with schedule="@daily" and catchup=True —
unpausing this DAG makes Airflow automatically create 5 backfill runs (one
per missed day) instead of just starting fresh from today:

    docker exec airflow-scheduler airflow dags unpause example_backfill

Watch it happen in the Grid view, or:

    docker exec airflow-scheduler airflow dags list-runs example_backfill

For an *already-running* DAG, ad-hoc backfill of an arbitrary historical
range (regardless of catchup) is a separate, explicit command:

    docker exec airflow-scheduler airflow backfill create \\
        --dag-id example_backfill --from-date 2026-07-01 --to-date 2026-07-05
"""

from datetime import datetime, timedelta

from airflow.sdk import dag, task


@dag(
    dag_id="example_backfill",
    description="Starter example: catchup fills in missed historical runs on unpause",
    doc_md=__doc__,
    start_date=datetime.now() - timedelta(days=5),
    schedule="@daily",
    catchup=True,
    tags=["example"],
)
def example_backfill():
    @task
    def process_day(**context) -> None:
        print(f"Processing logical date: {context['logical_date']}")

    process_day()


example_backfill()
