"""Starter example — a DAG that runs one task as its own resource-limited
container via DockerOperator, using the socket mounted into airflow-scheduler
(see docs/services/airflow/airflow.md's "DAGs can launch their own containers"
section). Delete this file, or use it as a template for a real DAG."""

from datetime import datetime

from airflow import DAG
from airflow.providers.docker.operators.docker import DockerOperator

with DAG(
    dag_id="example_docker_operator",
    description="Starter example: run one task in a resource-limited container",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
) as dag:
    hello = DockerOperator(
        task_id="hello_from_container",
        image="alpine:3.21",
        command=["echo", "hello from a resource-limited container"],
        mem_limit="128m",
        cpus=1.0,
        docker_url="unix://var/run/docker.sock",
        network_mode="homeserver",
        auto_remove="success",
    )
