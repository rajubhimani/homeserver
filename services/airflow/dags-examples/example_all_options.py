"""Reference DAG — every `@dag` and `@task` option in one place, each shown
at its real default value with a one-line explanation, so the whole menu
is visible without reading Airflow's source or hunting the docs site.

Only a handful of these are commonly touched in practice; those are set
for real below. Everything else is listed **commented-out, at its actual
default** inside the same `@dag(...)`/`@task(...)` calls — a checklist to
copy from, not a live example, since most of it (RBAC, executor pools,
callbacks...) needs infrastructure this repo's other example DAGs don't
set up. Uncomment + edit only what your own DAG actually needs.

Captured against Airflow 3.3.1 (`docker exec airflow-scheduler airflow
version`) via `inspect.signature()` against `airflow.sdk.definitions.dag.DAG`
and `airflow.sdk.bases.operator.BaseOperator` — the real source of truth if
this ever drifts from a future Airflow version. `sla`/`sla_miss_callback`
are Airflow 2.x concepts removed in 3.0 (`deadline`/`DeadlineAlert` is the
replacement, itself omitted below as too new/narrow for a first pass).
"""

from datetime import datetime, timedelta

from airflow.sdk import dag, task
from airflow.utils.trigger_rule import TriggerRule
from airflow.utils.weight_rule import WeightRule


@dag(
    # --- commonly set ---
    dag_id="example_all_options",
    description="Reference: every @dag/@task option, real defaults documented inline",
    doc_md=__doc__,
    schedule=None,  # None = manual trigger only. Also accepts a cron string, "@daily", a timedelta, or an Asset list.
    start_date=datetime(2026, 1, 1),  # no framework default — required, either here or per-task
    catchup=False,  # real default (scheduler.catchup_by_default in airflow.cfg) — True backfills missed runs on unpause, see example_backfill.py
    tags=["example"],
    # --- everything below: commented out, shown at its real default ---
    # end_date=None,                       # stop scheduling new runs after this date
    # max_active_tasks=16,                 # concurrent task instances allowed per DAG run (airflow.cfg: max_active_tasks_per_dag)
    # max_active_runs=16,                  # concurrent runs allowed for this DAG (see example_max_active_runs.py for =1, serial execution)
    # max_consecutive_failed_dag_runs=0,   # auto-pause this DAG after N consecutive failed runs (0 = never)
    # dagrun_timeout=None,                 # timedelta — fail a whole run that's been going longer than this
    # deadline=None,                       # DeadlineAlert(s) — Airflow 3's SLA replacement, alert if a run isn't done by a computed deadline
    # default_args={},                     # dict merged into every task's own kwargs below — set retries/owner/etc. once for the whole DAG instead of per task
    # params={},                           # DAG-level runtime parameters, editable per-trigger in the UI ("Trigger DAG w/ config") — see example_variables_and_connections.py for the Variables/Connections alternative
    # access_control=None,                 # per-DAG RBAC — {"role_name": {"can_read", "can_edit"...}}
    # is_paused_upon_creation=None,        # None defers to core.dags_are_paused_at_creation (True) — False = auto-unpaused the moment it's deployed
    # render_template_as_native_obj=False, # Jinja renders {{ }} to native Python types (int/list/dict) instead of always str
    # owner_links={},                      # {"owner_name": "https://link"} — clickable owner chip in the UI
    # dag_display_name=None,               # pretty name shown in the UI instead of the raw dag_id
    # fail_fast=False,                     # True = stop scheduling every remaining task the instant one fails, instead of letting independent branches keep running
    # allowed_run_types=None,              # restrict which DagRunType values (scheduled/manual/backfill/asset_triggered) may create a run
    # template_searchpath=None,            # extra filesystem paths Jinja searches for template files
    # user_defined_macros=None,            # extra names available inside {{ }} templates
    # user_defined_filters=None,           # extra Jinja filters usable inside {{ }} templates
    # jinja_environment_kwargs=None,       # raw kwargs passed straight to the underlying jinja2.Environment
    # task_group=...,                      # advanced/internal — the DAG's own root TaskGroup, auto-created; only override if you're doing custom TaskGroup composition
    # auto_register=True,                  # advanced/internal — whether entering this DAG's context manager auto-registers it; @dag-decorated DAGs never need this touched
    # disable_bundle_versioning=False,     # advanced — opt this DAG out of DAG-bundle version pinning (multi-version DAG bundles), irrelevant to this repo's single-bundle setup
    # rerun_with_latest_version=None,      # advanced — companion to bundle versioning above
)
def example_all_options():
    @task(
        # --- commonly set ---
        task_id="reference_task",  # only genuinely required arg — everything else below has a real default
        # --- everything below: commented out, shown at its real default ---
        # owner="airflow",                     # shown in the UI, filterable
        # retries=0,                           # retry attempts on failure — see example_scheduled_with_retries.py
        # retry_delay=timedelta(seconds=300),  # wait between retries
        # retry_exponential_backoff=False,     # multiply retry_delay by 2^attempt instead of a fixed wait
        # max_retry_delay=None,                # cap on the delay once exponential backoff is enabled
        # execution_timeout=None,              # timedelta — fail this task instance if it runs longer than this
        # depends_on_past=False,               # True = this run waits for *yesterday's* run of the same task to succeed first
        # wait_for_downstream=False,           # True = don't start until the *previous* run's immediate downstream tasks also finished
        # trigger_rule=TriggerRule.ALL_SUCCESS,  # when this task may run relative to upstream state — see example_trigger_rules.py for the other 8 values
        # priority_weight=1,                   # higher = scheduled first when a pool/queue is contended
        # weight_rule=WeightRule.DOWNSTREAM,   # how priority_weight combines with downstream tasks' own weights
        # queue="default",                     # Celery queue name — irrelevant under this repo's LocalExecutor, matters with CeleryExecutor
        # pool=None,                           # named resource pool capping concurrent tasks (Admin -> Pools) — e.g. cap concurrent access to one scarce DB
        # pool_slots=1,                        # how many pool slots one instance of this task consumes
        # executor=None,                       # override which Executor runs just this task (mixed-executor setups only)
        # executor_config=None,                # executor-specific config, e.g. KubernetesExecutor pod overrides
        # do_xcom_push=True,                   # False = don't publish this task's return value to XCom at all
        # multiple_outputs=False,              # True = unpack a dict return value into separate named XCom entries instead of one blob
        # map_index_template=None,             # custom per-instance label for dynamically mapped tasks — see example_dynamic_task_mapping.py
        # max_active_tis_per_dag=None,         # cap concurrent instances of *this task* across all of this DAG's runs
        # max_active_tis_per_dagrun=None,      # cap concurrent instances of *this task* within one DAG run (mapped tasks)
        # on_execute_callback=None,            # callable(context) fired right before the task runs
        # on_failure_callback=None,            # callable(context) fired on task failure — see example_email_alert_on_failure.py
        # on_success_callback=None,            # callable(context) fired on task success
        # on_retry_callback=None,              # callable(context) fired when a retry is about to happen
        # on_skipped_callback=None,            # callable(context) fired when the task is skipped
        # inlets=None,                         # declared upstream Datasets/Assets this task reads (lineage)
        # outlets=None,                        # declared Datasets/Assets this task produces — powers example_asset_triggered.py-style DAGs
        # task_display_name=None,              # pretty name shown in the UI instead of the raw task_id
        # doc_md=None,                         # per-task docs, its own Details -> Docs tab (separate from the DAG-level doc_md above)
        # run_as_user=None,                    # OS user to impersonate when running (LocalExecutor; needs sudoers set up on the host)
        # allow_nested_operators=True,         # False = raise instead of silently allowing this operator to invoke another operator's .execute() inside it
    )
    def reference_task() -> str:
        return "This task exists to document options, not to do real work."

    reference_task()


example_all_options()
