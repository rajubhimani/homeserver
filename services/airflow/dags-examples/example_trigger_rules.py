"""Starter example — trigger rules: what condition on its upstream tasks a
task needs before Airflow will run it. Every other example here uses the
implicit default (`all_success` — every upstream must succeed), which is why
none of them have a task that runs *because something else failed*. This is
the "always clean up, always alert on failure" shape almost every real DAG
needs somewhere.

    risky_task                              (deliberately fails every run)
      -> cleanup            trigger_rule=ALL_DONE     (runs no matter what — success or failure)
      -> alert_on_failure   trigger_rule=ONE_FAILED   (runs only because something upstream failed)
      -> only_if_all_ok     default (ALL_SUCCESS)     (never runs here — risky_task always fails)

Trigger this DAG and open the Grid view: `risky_task` is red, `cleanup` and
`alert_on_failure` are green (they *ran*, and succeeded, precisely because
the upstream failed), and `only_if_all_ok` is grey/skipped — Airflow never
even attempts a default-trigger-rule task once one of its upstreams fails.

Without a trigger rule override, a failed task cascades into every
downstream task being skipped, including your own cleanup/notification
logic — the two rules used here are how you opt specific tasks out of that
cascade instead of hand-rolling try/except failure-catching inside a
PythonOperator.
"""

from datetime import datetime

from airflow.sdk import dag, task
from airflow.task.trigger_rule import TriggerRule


@dag(
    dag_id="example_trigger_rules",
    description="Starter example: trigger_rule controls whether a task runs after an upstream failure",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_trigger_rules():
    @task
    def risky_task() -> None:
        # Real version: a step that can genuinely fail (a flaky API, a
        # source system that's sometimes down) — deliberately always fails
        # here so every run demonstrates the same trigger-rule behavior.
        raise ValueError("Simulated failure — this task is designed to always fail")

    @task(trigger_rule=TriggerRule.ALL_DONE)
    def cleanup() -> None:
        # Real version: release a lock, delete a temp file, close a
        # connection — things that must happen whether risky_task succeeded
        # or not.
        print("Cleanup ran — this always happens, success or failure upstream.")

    @task(trigger_rule=TriggerRule.ONE_FAILED)
    def alert_on_failure() -> None:
        # Real version: post to ntfy/Slack/PagerDuty. This task's only job
        # is to exist for the failure case — with the default trigger rule
        # it would never run at all, since its upstream never succeeds.
        print("ALERT: risky_task failed — this task exists to run *because* of that.")

    @task
    def only_if_all_ok() -> None:
        # Default trigger rule (ALL_SUCCESS) — included as the contrast case.
        # This never actually runs in this DAG, because risky_task always
        # fails: Airflow marks it upstream_failed / skipped, visible in the
        # Grid view as grey next to cleanup/alert_on_failure's green.
        print("This only prints if risky_task actually succeeded.")

    started = risky_task()
    started >> cleanup()
    started >> alert_on_failure()
    started >> only_if_all_ok()


example_trigger_rules()
