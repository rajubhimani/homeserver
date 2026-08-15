"""Starter example — the simplest possible DAG: one task, no dependencies,
no data passed anywhere. Start here before the others if DAGs are new to
you; example_etl_pipeline.py is the next step up (task chaining + XCom)."""

from datetime import datetime

from airflow.sdk import dag, task


@dag(
    dag_id="example_hello_world",
    description="Starter example: the simplest possible DAG",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_hello_world():
    @task
    def hello() -> None:
        print("Hello from Airflow!")

    hello()


example_hello_world()
