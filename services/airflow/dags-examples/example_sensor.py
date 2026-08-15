"""Starter example — a Sensor: "don't run the next task until X is true,"
a signature Airflow concept distinct from the task-chaining examples. This
one waits for a marker file to appear rather than needing a pre-configured
Connection, so it works with zero setup — trigger the DAG, then from another
terminal:

    touch service_data/data/airflow/dags/.sensor_trigger

...and watch the sensor task go from running to success within ~10s (its
poke_interval). Delete the marker file afterward if you want to run it
again — it stays green, but this makes re-triggering cleanly reproducible.
"""

from datetime import datetime, timedelta
from pathlib import Path

from airflow.sdk import PokeReturnValue, dag, task

MARKER_FILE = Path("/opt/airflow/dags/.sensor_trigger")


@dag(
    dag_id="example_sensor",
    description="Starter example: wait for a condition before proceeding",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_sensor():
    @task.sensor(poke_interval=10, timeout=timedelta(minutes=10), mode="reschedule")
    def wait_for_marker_file() -> PokeReturnValue:
        found = MARKER_FILE.exists()
        return PokeReturnValue(is_done=found, xcom_value=str(MARKER_FILE) if found else None)

    @task
    def proceed(marker_path: str) -> None:
        print(f"Marker file appeared at {marker_path} — proceeding.")

    proceed(wait_for_marker_file())


example_sensor()
