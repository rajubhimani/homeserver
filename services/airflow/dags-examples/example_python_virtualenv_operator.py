"""Starter example — `PythonVirtualenvOperator`: runs a callable inside a
fresh, isolated venv with its own `requirements`, instead of whatever's
already installed in `airflow-scheduler`'s own environment. Real fit: one
task needs a specific/conflicting package version the rest of the DAG
doesn't, without touching `_PIP_ADDITIONAL_REQUIREMENTS` (which installs
into the scheduler's environment for every task, see compose.yml) or
building a dedicated custom image.

Honest limitation, not glossed over: this rebuilds the venv **every run**
unless `venv_cache_path` is set (not set here, for simplicity) — fine for
a homelab's occasional task, a real production cost at high task-run
volume. `system_site_packages=False` below means the callable genuinely
can't see Airflow's own installed packages either — only what's listed in
`requirements`, plus the stdlib.

    docker exec airflow-scheduler airflow dags unpause example_python_virtualenv_operator
    docker exec airflow-scheduler airflow dags trigger example_python_virtualenv_operator
"""

from datetime import datetime

from airflow.providers.standard.operators.python import PythonVirtualenvOperator
from airflow.sdk import dag


def print_emoji() -> None:
    # Real version: any callable needing a package/version the rest of the
    # DAG doesn't have. Must import everything it uses *inside* the
    # function body — this runs in a separate subprocess/venv, so it can't
    # see names imported at module level in this file.
    import emoji

    print(emoji.emojize("Task ran inside an isolated venv :thumbs_up:"))


@dag(
    dag_id="example_python_virtualenv_operator",
    description="Starter example: PythonVirtualenvOperator — an isolated venv with its own requirements, per task",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_python_virtualenv_operator():
    PythonVirtualenvOperator(
        task_id="run_in_isolated_venv",
        python_callable=print_emoji,
        requirements=["emoji"],
        system_site_packages=False,
    )


example_python_virtualenv_operator()
