"""Starter example — three built-in flow-control operators, distinct from
`BranchPythonOperator` (see `example_branching.py`) and `trigger_rule`
(see `example_trigger_rules.py`), each independent of the other two below:

    ShortCircuitOperator   — skip *every* downstream task on a falsy
                              return, not route between named branches
                              like BranchPythonOperator does.
    LatestOnlyOperator      — skip downstream unless this run is the DAG's
                              most recent *scheduled* run — the real-world
                              case is "don't let a backfill re-trigger a
                              notification task." schedule="@daily" +
                              catchup=True + a start_date 3 days back means
                              unpausing creates the same kind of backfill
                              runs example_backfill.py does; only the most
                              recent of those 3 should reach
                              notify_only_if_latest.
    BranchDayOfWeekOperator — declarative day-of-week branching, no
                              hand-written BranchPythonOperator callable
                              needed for this specific, common case.

    docker exec airflow-scheduler airflow dags unpause example_flow_control
    docker exec airflow-scheduler airflow dags list-runs example_flow_control
"""

from datetime import datetime, timedelta

from airflow.providers.standard.operators.empty import EmptyOperator
from airflow.providers.standard.operators.latest_only import LatestOnlyOperator
from airflow.providers.standard.operators.python import ShortCircuitOperator
from airflow.providers.standard.operators.weekday import BranchDayOfWeekOperator
from airflow.providers.standard.utils.weekday import WeekDay
from airflow.sdk import dag, task


@dag(
    dag_id="example_flow_control",
    description="Starter example: ShortCircuitOperator, LatestOnlyOperator, BranchDayOfWeekOperator",
    doc_md=__doc__,
    start_date=datetime.now() - timedelta(days=3),
    schedule="@daily",
    catchup=True,
    tags=["example"],
)
def example_flow_control():
    # --- LatestOnlyOperator: only the most recent of the 3 backfilled runs
    # reaches notify_only_if_latest; the other 2 show it `skipped`.
    latest_only = LatestOnlyOperator(task_id="latest_only")

    @task
    def notify_only_if_latest() -> None:
        print("This only runs for the current run, not a backfilled one.")

    latest_only >> notify_only_if_latest()

    # --- ShortCircuitOperator: a falsy return skips every downstream task
    # at once, not just one named branch.
    def feature_flag_enabled() -> bool:
        # Real version: check a Variable/Connection/env value.
        return True

    short_circuit = ShortCircuitOperator(task_id="short_circuit", python_callable=feature_flag_enabled)

    @task
    def do_expensive_work() -> None:
        print("Only reached if the short-circuit check passed.")

    short_circuit >> do_expensive_work()

    # --- BranchDayOfWeekOperator: declarative day-of-week branching.
    weekday_branch = BranchDayOfWeekOperator(
        task_id="is_weekend",
        follow_task_ids_if_true="weekend_task",
        follow_task_ids_if_false="weekday_task",
        week_day={WeekDay.SATURDAY, WeekDay.SUNDAY},
    )
    weekend_task = EmptyOperator(task_id="weekend_task")
    weekday_task = EmptyOperator(task_id="weekday_task")
    weekday_branch >> [weekend_task, weekday_task]


example_flow_control()
