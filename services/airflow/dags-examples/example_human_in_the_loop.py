"""Starter example — Airflow's own built-in Human-in-the-Loop (HITL, new in
3.1): pause a task until a human responds through the UI, no Signal-handling
code to write yourself. This is the direct built-in parallel to Temporal's
`ApprovalWorkflow` (`workflow.wait_condition()` + a `@workflow.signal`) —
same underlying idea, "durably wait for a human decision," different
mechanism: Temporal's version is your own workflow code waiting on a
Signal; Airflow's is a single operator that suspends and shows its own
dedicated `awaiting_input` state (distinct from `deferred` — this doesn't
even hold a slot in `airflow-triggerer` the way
`example_deferrable_sensor.py`/`example_file_sensor.py`'s deferred mode
does; HITL waits are tracked directly, no trigger involved) until a human
responds via the UI's **Human-in-the-loop** tab or the REST API directly.

`ApprovalOperator` is the simplest form — fixed "Approve"/"Reject" choices,
nothing to configure per call. `HITLEntryOperator` (not used here, kept out
to stay focused on the direct Temporal comparison) is the general form:
arbitrary options, free-text input, validated form fields via `params`.

Trigger it, then respond once `approval_gate` shows `awaiting_input` in
the Grid view — either the UI's Human-in-the-loop tab, or the same PATCH
call directly (run this from the host, against the dev port):

    docker exec airflow-scheduler airflow dags unpause example_human_in_the_loop
    docker exec airflow-scheduler airflow dags trigger example_human_in_the_loop

    # get a bearer token (same admin login the UI uses), then respond:
    TOKEN=$(curl -s -X POST http://localhost:8137/auth/token \\
        -H 'Content-Type: application/json' \\
        -d '{"username": "admin", "password": "<_AIRFLOW_WWW_USER_PASSWORD>"}' \\
        | python3 -c 'import sys,json; print(json.load(sys.stdin)["access_token"])')

    RUN_ID=$(docker exec airflow-scheduler airflow dags list-runs example_human_in_the_loop \\
        | tail -1 | awk -F'|' '{print $2}' | xargs)

    curl -s -X PATCH \\
        "http://localhost:8137/api/v2/dags/example_human_in_the_loop/dagRuns/${RUN_ID}/taskInstances/approval_gate/-1/hitlDetails" \\
        -H "Authorization: Bearer ${TOKEN}" -H 'Content-Type: application/json' \\
        -d '{"chosen_options": ["Approve"]}'   # or ["Reject"]

`ApprovalOperator` is a gate, not a branch router: "Approve" lets
`proceed` run normally; "Reject" **skips** `proceed` (not a failure —
`fail_on_reject=True` would make it one instead, deliberately not set
here, see the operator's own docstring for why that's discouraged).
Trigger this DAG twice — once approving, once rejecting — to see both:
`proceed` ends up `success` the first time, `skipped` the second.
"""

from datetime import datetime

from airflow.providers.standard.operators.hitl import ApprovalOperator
from airflow.sdk import dag, task


@dag(
    dag_id="example_human_in_the_loop",
    description="Starter example: built-in Human-in-the-Loop approval gate — the direct parallel to Temporal's ApprovalWorkflow",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_human_in_the_loop():
    approval_gate = ApprovalOperator(
        task_id="approval_gate",
        subject="Approve the (real) next step?",
        body="Real version: e.g. approve a spend, a deploy, a destructive migration step before it runs.",
    )

    @task
    def proceed() -> str:
        return "Approved — proceeding with the (real) next step."

    approval_gate >> proceed()


example_human_in_the_loop()
