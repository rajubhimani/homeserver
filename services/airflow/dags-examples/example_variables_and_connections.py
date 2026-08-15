"""Starter example — Airflow's own lightweight secrets/config store:
Variables (any string or JSON value) and Connections (structured
credentials — host/login/password/extra), both encrypted at rest in
Airflow's own metadata DB via `FERNET_KEY`. No external secrets manager
needed for homelab-scale pipeline credentials — see docs/12-orchestration.md's
"Built-in features that mean you don't need another service."

Variables: set and read back entirely from inside this DAG, JSON-serialized.

Connections: realistically admin-provisioned once, not created from inside
a DAG on every run — same as how a human sets up a database credential a
single time, not on every pipeline execution. Create the demo one first,
then trigger:

    docker exec airflow-scheduler airflow connections add demo_api_connection \\
        --conn-type http --conn-host api.example.com --conn-login demo_user --conn-password super-secret-value

    docker exec airflow-scheduler airflow dags unpause example_variables_and_connections
    docker exec airflow-scheduler airflow dags trigger example_variables_and_connections

Prove it's genuinely encrypted, not plaintext, straight from the DB — the
password column should be an unreadable Fernet blob, not "super-secret-value":

    docker exec airflow-db psql -U airflow -c "SELECT conn_id, password FROM connection WHERE conn_id='demo_api_connection';"
"""

from datetime import datetime

from airflow.sdk import BaseHook, Variable, dag, task


@dag(
    dag_id="example_variables_and_connections",
    description="Starter example: Airflow's own encrypted Variable/Connection store, no external secrets manager needed",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_variables_and_connections():
    @task
    def set_and_read_variable() -> None:
        Variable.set("demo_config", {"retries": 3, "timeout_seconds": 30}, serialize_json=True)
        config = Variable.get("demo_config", deserialize_json=True)
        print(f"Read back Variable 'demo_config': {config}")

    @task
    def read_connection() -> None:
        conn = BaseHook.get_connection("demo_api_connection")
        # Real version: use conn.host/conn.login/conn.password/conn.extra_dejson
        # to actually call the API. conn.password is decrypted here, in memory,
        # for this task's own process only — never written back out in plain text.
        masked = "*" * len(conn.password or "")
        print(f"Connection 'demo_api_connection': host={conn.host} login={conn.login} password={masked}")

    set_and_read_variable() >> read_connection()


example_variables_and_connections()
