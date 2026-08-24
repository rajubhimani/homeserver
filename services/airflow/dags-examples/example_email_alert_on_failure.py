"""Starter example — email alerting on task failure, actually working end to
end. `AIRFLOW__EMAIL__DEFAULT_EMAIL_ON_FAILURE`/`ON_RETRY` are documented in
`.env.example` but silently no-op without a real SMTP target — `compose.yml`
points `airflow-scheduler` at a bundled Mailpit catcher (`mailpit`, container
`airflow-mailpit`) for exactly this reason: nothing leaves this host, but the
mechanism genuinely fires and you can watch it land.

This task always fails, on purpose, with `email_on_failure=True` and a real
`email=` recipient — trigger it, then check Mailpit's inbox:

    docker exec airflow-scheduler airflow dags unpause example_email_alert_on_failure
    docker exec airflow-scheduler airflow dags trigger example_email_alert_on_failure

Web UI: http://<host>:8140 (dev) — or the REST API directly:

    curl -s http://localhost:8140/api/v1/messages | python3 -m json.tool
"""

from datetime import datetime

from airflow.sdk import dag, task


@dag(
    dag_id="example_email_alert_on_failure",
    description="Starter example: a real failure email, caught by the bundled Mailpit SMTP catcher",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_email_alert_on_failure():
    @task(email="demo-alerts@homeserver.local", email_on_failure=True, retries=0)
    def always_fails() -> None:
        # Real version: whatever step you actually want paged on. Always
        # raises here so every run demonstrates the same alert.
        raise RuntimeError("Simulated failure — this task always fails to trigger the alert email")

    always_fails()


example_email_alert_on_failure()
