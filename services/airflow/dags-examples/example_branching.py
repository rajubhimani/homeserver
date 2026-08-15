"""Starter example — BashOperator for a plain shell command, plus conditional
branching (BranchPythonOperator): a very common real-world need — e.g. "only
run the expensive step if today's check found new data"."""

import random
from datetime import datetime

from airflow import DAG
from airflow.providers.standard.operators.bash import BashOperator
from airflow.providers.standard.operators.python import BranchPythonOperator, PythonOperator


def check_for_new_data() -> str:
    # Real version: query an API/DB/file listing. This just simulates a
    # 50/50 result so the branch actually alternates across runs.
    return "process_new_data" if random.random() < 0.5 else "skip_no_data"


def process() -> None:
    print("Processing new data...")


with DAG(
    dag_id="example_branching",
    description="Starter example: shell command + conditional branch",
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
) as dag:
    check_disk_space = BashOperator(
        task_id="check_disk_space",
        bash_command="df -h /opt/airflow",
    )

    branch = BranchPythonOperator(
        task_id="check_for_new_data",
        python_callable=check_for_new_data,
    )

    process_new_data = PythonOperator(
        task_id="process_new_data",
        python_callable=process,
    )

    skip_no_data = BashOperator(
        task_id="skip_no_data",
        bash_command="echo 'Nothing new — skipping.'",
    )

    check_disk_space >> branch >> [process_new_data, skip_no_data]
