"""Starter example — a custom `BaseNotifier` subclass: a reusable,
parameterized notification target instead of a bare `on_failure_callback`
function. `example_email_alert_on_failure.py` already exercises a
*built-in* Notifier (`SmtpNotifier`, wired up implicitly by
`email_on_failure=True`) — this shows writing your own, Dagster's
`@success_hook`/`@failure_hook` parallel on the Airflow side (see
docs/12-orchestration.md's feature-parity table).

A plain function callback works fine for a one-off; a `BaseNotifier`
subclass is worth it once the same notification target (a file, a
webhook, a ticketing system) gets reused across several tasks/DAGs with
different messages each time — `template_fields` makes the message itself
Jinja-templatable per call, the same as any operator argument.

    docker exec airflow-scheduler airflow dags unpause example_custom_notifier
    docker exec airflow-scheduler airflow dags trigger example_custom_notifier
    docker exec airflow-scheduler cat /opt/airflow/dags/.custom_notifier_log
"""

from datetime import datetime

from airflow.sdk import dag, task
from airflow.sdk.bases.notifier import BaseNotifier

LOG_PATH = "/opt/airflow/dags/.custom_notifier_log"


class LocalFileNotifier(BaseNotifier):
    """Real version: POST to a webhook/ticketing API instead of writing a
    local file. The point demonstrated here is the class itself being
    reusable/parameterized/templated, not the destination."""

    template_fields = ("message",)

    def __init__(self, message: str) -> None:
        super().__init__()
        self.message = message

    def notify(self, context) -> None:
        with open(LOG_PATH, "a") as f:
            f.write(f"{self.message}\n")


@dag(
    dag_id="example_custom_notifier",
    description="Starter example: a custom BaseNotifier subclass, reusable/templated notification target",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_custom_notifier():
    @task(
        on_failure_callback=LocalFileNotifier(message="ALERT: {{ ti.task_id }} failed in {{ dag.dag_id }}"),
    )
    def always_fails() -> None:
        raise ValueError("Simulated failure — on_failure_callback fires the custom Notifier.")

    always_fails()


example_custom_notifier()
