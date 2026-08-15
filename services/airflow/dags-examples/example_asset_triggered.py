"""Starter example — Airflow's Asset feature (renamed from "Dataset" in
Airflow 3.0): a *label* a task's output is tagged with (outlets=), used to
trigger a *different* DAG when that label updates. Not the same thing as a
Dagster asset — see docs/12-orchestration.md for the real
distinction. Two DAGs:

  example_asset_producer  — a task that updates the Asset (outlets=)
  example_asset_consumer  — scheduled to run whenever that Asset updates

Trigger the producer manually once; the consumer run appears on its own
shortly after, with no manual trigger and no cron schedule of its own.
"""

from datetime import datetime

from airflow.sdk import Asset, dag, task

report_asset = Asset("homeserver://example/report")


@dag(
    dag_id="example_asset_producer",
    description="Starter example: a task that updates an Asset",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_asset_producer():
    @task(outlets=[report_asset])
    def produce_report() -> None:
        print("Report produced — this updates the homeserver://example/report Asset.")

    produce_report()


@dag(
    dag_id="example_asset_consumer",
    description="Starter example: scheduled to run when the Asset above updates",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=[report_asset],
    catchup=False,
    tags=["example"],
)
def example_asset_consumer():
    @task
    def on_report_updated() -> None:
        print("Triggered automatically because homeserver://example/report was updated.")

    on_report_updated()


example_asset_producer()
example_asset_consumer()
