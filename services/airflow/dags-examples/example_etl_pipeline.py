"""Starter example — classic extract/transform/load task chain using
TaskFlow's @task decorator, with data passed between tasks via XCom
(return values are automatically passed to the next task's arguments)."""

from datetime import datetime

from airflow.sdk import dag, task


@dag(
    dag_id="example_etl_pipeline",
    description="Starter example: extract -> transform -> load task chain",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_etl_pipeline():
    @task
    def extract() -> list[dict]:
        return [{"id": 1, "value": 10}, {"id": 2, "value": 20}, {"id": 3, "value": 30}]

    @task
    def transform(records: list[dict]) -> dict:
        total = sum(r["value"] for r in records)
        return {"count": len(records), "total": total, "average": total / len(records)}

    @task
    def load(summary: dict) -> None:
        print(f"Loaded summary: {summary}")

    load(transform(extract()))


example_etl_pipeline()
