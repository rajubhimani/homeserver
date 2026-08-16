"""Starter example — making one DAG depend on another, Airflow's two
built-in ways to do it. Neither needs a Sensor/Trigger you write yourself
(see example_file_sensor.py's docstring for that same point about waiting
on a file) — both ship in `apache-airflow-providers-standard`, already
installed in this stack:

  ExternalTaskSensor  — the "pull" direction: waiter_dag waits for a
                         specific task in producer_dag's run to reach a
                         given state. Matches by logical_date by default —
                         trigger both with the *same* one to see it work:

    docker exec airflow-scheduler airflow dags unpause producer_dag
    docker exec airflow-scheduler airflow dags unpause waiter_dag
    docker exec airflow-scheduler airflow dags trigger producer_dag --logical-date 2026-01-02T00:00:00+00:00
    docker exec airflow-scheduler airflow dags trigger waiter_dag --logical-date 2026-01-02T00:00:00+00:00

  TriggerDagRunOperator — the "push" direction: trigger_only_dag actively
                          starts a *fresh* run of producer_dag itself
                          (its own new logical_date, no matching needed)
                          and, with wait_for_completion=True, blocks until
                          that run finishes — the closest built-in analog
                          to Temporal's execute_child_workflow or Dagster's
                          RunRequest, minus their independent Event
                          History/asset lineage.

    docker exec airflow-scheduler airflow dags unpause trigger_only_dag
    docker exec airflow-scheduler airflow dags trigger trigger_only_dag

Watch either in the Grid view — waiter_dag's `wait_for_producer` task shows
`deferred` while it waits, same zero-worker-slot mechanism as
example_deferrable_sensor.py/example_file_sensor.py's deferred mode.
"""

from datetime import datetime, timedelta

from airflow.providers.standard.operators.trigger_dagrun import TriggerDagRunOperator
from airflow.providers.standard.sensors.external_task import ExternalTaskSensor
from airflow.sdk import dag, task

DAG_KWARGS = dict(
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)


@dag(dag_id="producer_dag", description="Cross-DAG example: the DAG being waited on / triggered", **DAG_KWARGS)
def producer_dag():
    @task(task_id="do_work")
    def do_work() -> str:
        return "producer_dag's work is done"

    do_work()


@dag(
    dag_id="waiter_dag",
    description="Cross-DAG example: ExternalTaskSensor — waits (pulls) for producer_dag's task, matched by logical_date",
    doc_md=__doc__,
    **DAG_KWARGS,
)
def waiter_dag():
    wait_for_producer = ExternalTaskSensor(
        task_id="wait_for_producer",
        external_dag_id="producer_dag",
        external_task_id="do_work",
        poll_interval=10,
        timeout=timedelta(minutes=10),
        deferrable=True,  # same zero-worker-slot wait as example_file_sensor.py's deferred_mode_task
    )

    @task
    def report() -> None:
        print("producer_dag's do_work task reached a matching state — proceeding.")

    wait_for_producer >> report()


@dag(
    dag_id="trigger_only_dag",
    description="Cross-DAG example: TriggerDagRunOperator — actively starts (pushes) a fresh producer_dag run and waits for it",
    **DAG_KWARGS,
)
def trigger_only_dag():
    TriggerDagRunOperator(
        task_id="trigger_producer",
        trigger_dag_id="producer_dag",
        wait_for_completion=True,
        poke_interval=5,
        deferrable=True,  # same zero-worker-slot wait while blocked on the triggered run
    )


producer_dag()
waiter_dag()
trigger_only_dag()
