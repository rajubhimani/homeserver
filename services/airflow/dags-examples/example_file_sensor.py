"""Starter example — the built-in `FileSensor`, Airflow's own out-of-the-box
answer to "wait for a file to appear," in both modes `example_sensor.py`
and `example_deferrable_sensor.py` hand-roll from scratch. Those two exist
to make the poke/reschedule and defer-into-the-triggerer *mechanisms*
visible for teaching — not because Airflow lacks the feature. This file is
the other half of that story: the same wait, using what ships in
`apache-airflow-providers-standard` (already installed in this stack),
zero custom Trigger/Sensor code required.

    poke_mode_task    — FileSensor(deferrable=False), same poke/reschedule
                         loop as example_sensor.py's hand-rolled @task.sensor
    deferred_mode_task — FileSensor(deferrable=True), same suspend-into-
                         airflow-triggerer mechanism as example_deferrable_sensor.py's
                         hand-rolled BaseTrigger

`FileSensor` reads its base path from an Airflow Connection (`fs_conn_id`,
default `fs_default`) — realistically admin-provisioned once, same as
`example_variables_and_connections.py`'s `demo_api_connection`. Create it,
then trigger:

    docker exec airflow-scheduler airflow connections add fs_default --conn-type fs

    docker exec airflow-scheduler airflow dags unpause example_file_sensor
    docker exec airflow-scheduler airflow dags trigger example_file_sensor

Then, from another terminal, create either marker file and watch that one
task go from `running`/`deferred` to `success` within ~10s:

    docker exec airflow-scheduler touch /opt/airflow/dags/.file_sensor_poke_trigger
    docker exec airflow-scheduler touch /opt/airflow/dags/.file_sensor_deferred_trigger

Watch `deferred_mode_task`'s state in the Grid view specifically — it
shows `deferred`, not `running`, the same distinct state
`example_deferrable_sensor.py` calls out, for the same reason: it isn't
holding a worker slot while it waits.
"""

from datetime import datetime, timedelta

from airflow.providers.standard.sensors.filesystem import FileSensor
from airflow.sdk import dag, task


@dag(
    dag_id="example_file_sensor",
    description="Starter example: the built-in FileSensor (poke + deferrable), vs. this repo's hand-rolled equivalents",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_file_sensor():
    poke_mode_task = FileSensor(
        task_id="poke_mode_task",
        filepath="/opt/airflow/dags/.file_sensor_poke_trigger",
        poke_interval=10,
        timeout=timedelta(minutes=10),
        mode="reschedule",  # same worker-slot-freeing choice example_sensor.py makes explicitly
        deferrable=False,  # the default — spelled out here since deferred_mode_task below is the whole point of the contrast
    )

    deferred_mode_task = FileSensor(
        task_id="deferred_mode_task",
        filepath="/opt/airflow/dags/.file_sensor_deferred_trigger",
        poke_interval=10,
        timeout=timedelta(minutes=10),
        deferrable=True,  # suspends into airflow-triggerer instead of polling from a worker — see example_deferrable_sensor.py for what this does under the hood
    )

    @task
    def report(which: str) -> None:
        print(f"{which} marker file appeared — proceeding.")

    poke_mode_task >> report.override(task_id="report_poke")("poke_mode_task")
    deferred_mode_task >> report.override(task_id="report_deferred")("deferred_mode_task")


example_file_sensor()
