"""Starter pipeline — replace with your own assets/jobs/schedules.

Things this is meant to show a new user:
1. hello_homeserver: the simplest possible asset.
2. raw_data -> cleaned_data -> report: Dagster's actual strength — assets
   are data, not steps. Dependencies are inferred from function parameter
   names (cleaned_data's `raw_data` argument IS the dependency declaration —
   no >> operator, no manual DAG wiring), and every materialization is
   automatically resource-bounded via docker_executor below, the same
   pattern as Airflow's DockerOperator and Temporal's worker (see
   docs/services/dagster/dagster.md and the other two services' docs).
3. report_freshness_check: an Asset Check — Dagster's built-in data-quality
   concept, distinct from Airflow/Temporal, which have no equivalent.
4. daily_sales: a partitioned asset — Dagster's actual answer to "backdated
   ingestion from a source system." Each partition (one per calendar day)
   materializes independently; backfilling old dates means materializing
   old partitions, not re-running the whole pipeline. See
   docs/12-orchestration.md for how this differs from
   Airflow's catchup/backfill (whole-DAG-run, not per-partition).
5. sales_sensor: reacts to an external signal (a marker file, same pattern
   as example_sensor.py in Airflow) instead of running on a fixed schedule.
6. report_notification: Declarative Automation — a third scheduling
   paradigm alongside report_daily_schedule (an explicit cron Schedule) and
   marker_file_sensor (an explicit external-event Sensor) above. Instead of
   either, this asset declares an AutomationCondition ("materialize me
   whenever my dependency updates") and dagster-daemon's built-in
   automation-condition sensor handles the rest — no schedule, no sensor
   function of your own to write.
7. source_system_summary + SourceSystemResource: a Resource — how you give
   an asset a configurable connection to something external (an API base
   URL, credentials) instead of hardcoding a client inline. The resource is
   itself just a config object; swapping environments means changing the
   Definitions(resources=...) value below, not the asset's code.
8. orders_multi_asset: @multi_asset — one function producing several assets
   atomically in a single materialization, sharing data in memory instead of
   each asset re-fetching or round-tripping through the IO manager. Real fit
   for tightly-coupled steps (a single API call that naturally yields a raw,
   a staged, and a validated view of the same batch).
9. ops_pipeline_job: the classic @op/@job style, included deliberately next
   to the asset examples above so the two are easy to compare. Ops wire
   together by explicit function calls (`b(a())`), not by Dagster inferring
   an edge from a parameter *name* the way assets do — reach for this when
   a pipeline genuinely isn't shaped around producing/tracking data (a batch
   of side-effecting steps), or you're integrating code that's already
   op-shaped. See docs/12-orchestration.md for when this fits vs. an asset.
10. customer_orders: the "catalog" side of Dagster — description, owners,
    kinds, and metadata (both static and computed at materialization time:
    row count, a markdown preview, a real column-by-column schema via
    TableSchema/TableColumn). None of the assets above set any of this;
    every one of them works without it, but this is what makes an asset's
    own page in the UI genuinely documentation instead of just a lineage
    node — the column schema in particular renders as a real table, not
    just text.
11. reference_asset / reference_op / reference_job / reference_schedule /
    reference_sensor: reference, not a pattern demo like everything above —
    every `@asset`/`@op`/`@job`/`ScheduleDefinition`/`@sensor` option in one
    place, each shown at its real default with a one-line explanation (a
    handful set for real, everything else commented-out as a checklist to
    copy from). Captured against this image's pinned Dagster version via
    `inspect.signature()` against each — the source of truth if this ever
    drifts from a future Dagster version. reference_schedule/reference_sensor
    both default to DefaultScheduleStatus.STOPPED/DefaultSensorStatus.STOPPED
    (Dagster's own real default — every schedule/sensor starts off until you
    flip it on from the Schedules/Sensors tab), so registering them here has
    zero effect until you do.
12. flaky_retry_asset: `retry_policy=RetryPolicy(max_retries=2, delay=2)` —
    the same "fails twice, succeeds on the third attempt" shape as
    Temporal's flaky_activity (services/temporal/worker/activities.py) and
    Airflow's example_scheduled_with_retries.py, so the three tools' retry
    stories are directly comparable. The interesting wrinkle here, not
    present in the other two: each retry is a *fresh step container*
    (docker_executor), so an in-memory attempt counter would just reset to
    0 every time — this persists the count to a file on the same
    io_manager_storage volume every asset here already shares, the same
    problem (and same kind of fix) Airflow's example_stateful_retry.py
    solves via the Task State Store instead of a plain module-level dict.
13. fan_out_a / fan_out_b / fan_out_c: 3 independent assets, no shared
    dependency between them, each in its own step container — proof (not
    just an assumption) that Dagster materializes independent assets
    concurrently, the direct analog of Airflow's example_parallel_tasks.py
    and Temporal's BatchProcessingWorkflow.
14. daily_sales_single_run: same shape as daily_sales above, with
    backfill_policy=BackfillPolicy.single_run() — backfilling a range of
    partitions launches exactly one run processing the whole range, not
    one run per partition like daily_sales's default.
15. ops_pipeline_job's log_job_success: a @success_hook, Dagster's parallel
    to Airflow's on_success_callback/custom Notifier — attached
    declaratively via @job(hooks=...) instead of passed as a callback
    argument, fires once per op (not once per whole job).
16. process_uploaded_file + new_file_sensor: a DynamicPartitionsDefinition
    — partitions created at runtime, by name, as files show up (tracked in
    Dagster's own metadata DB via add_dynamic_partitions), unlike
    daily_sales's fixed DailyPartitionsDefinition where every partition is
    known in advance.
"""

from pathlib import Path

from dagster import (
    AssetCheckResult,
    AssetExecutionContext,
    AssetOut,
    AutomationCondition,
    Backoff,
    BackfillPolicy,
    ConfigurableResource,
    DailyPartitionsDefinition,
    DefaultScheduleStatus,
    DefaultSensorStatus,
    Definitions,
    DynamicPartitionsDefinition,
    FilesystemIOManager,
    HookContext,
    Jitter,
    MetadataValue,
    Output,
    RetryPolicy,
    RunRequest,
    ScheduleDefinition,
    SensorEvaluationContext,
    SkipReason,
    TableColumn,
    TableSchema,
    asset,
    asset_check,
    define_asset_job,
    job,
    multi_asset,
    op,
    sensor,
    success_hook,
)
from dagster_docker import docker_executor


@asset
def hello_homeserver() -> str:
    return "Dagster is running — replace definitions.py with real assets."


@asset
def raw_data() -> list[dict]:
    # Real version: read from an API/DB/file. This is deliberately the same
    # shape as the Airflow ETL example (example_etl_pipeline.py) so the two
    # are easy to compare side by side.
    return [{"id": 1, "value": 10}, {"id": 2, "value": 20}, {"id": 3, "value": 30}]


@asset
def cleaned_data(raw_data: list[dict]) -> list[dict]:
    # The `raw_data` parameter name is the dependency declaration — Dagster
    # sees this function takes an asset called raw_data and wires the edge
    # automatically. No >> operator, no explicit DAG object.
    return [r for r in raw_data if r["value"] > 0]


@asset
def report(cleaned_data: list[dict]) -> dict:
    total = sum(r["value"] for r in cleaned_data)
    return {"count": len(cleaned_data), "total": total, "average": total / len(cleaned_data)}


@asset_check(asset=report)
def report_freshness_check(report: dict) -> AssetCheckResult:
    return AssetCheckResult(
        passed=report["count"] > 0,
        metadata={"count": report["count"]},
    )


@asset(automation_condition=AutomationCondition.eager())
def report_notification(report: dict) -> str:
    # Real version: post the report summary to ntfy/Slack. No schedule and
    # no sensor function needed — dagster-daemon's automation-condition
    # sensor materializes this automatically whenever `report` updates,
    # because that's what AutomationCondition.eager() declares.
    return f"Notified: report has {report['count']} rows, total {report['total']}"


report_job = define_asset_job(name="report_job", selection=[raw_data, cleaned_data, report])
report_daily_schedule = ScheduleDefinition(job=report_job, cron_schedule="0 6 * * *")


RETRY_COUNTER_PATH = Path("/tmp/io_manager_storage/.dagster_retry_counter")


@asset(retry_policy=RetryPolicy(max_retries=2, delay=2))
def flaky_retry_asset() -> str:
    # Real version: an actual flaky external call. A retry here launches a
    # *fresh* step container (docker_executor, same as every asset in this
    # file) — an in-memory counter, unlike Temporal's flaky_activity in
    # services/temporal/worker/activities.py, would just reset to 0 on
    # every attempt instead of remembering how many already happened. Same
    # reason Airflow's example_stateful_retry.py persists to an external
    # store instead of a plain module-level dict: this counter file (on the
    # same io_manager_storage volume every asset here already shares) is
    # this repo's Dagster answer to that identical problem.
    attempt = int(RETRY_COUNTER_PATH.read_text()) + 1 if RETRY_COUNTER_PATH.exists() else 1
    RETRY_COUNTER_PATH.write_text(str(attempt))
    if attempt < 3:
        raise Exception(f"simulated transient failure (attempt {attempt}/3)")
    RETRY_COUNTER_PATH.unlink(missing_ok=True)  # reset so the next materialization starts at attempt 1 again
    return f"succeeded on attempt {attempt} — Dagster retried this automatically, no retry loop written by hand"


flaky_retry_job = define_asset_job(name="flaky_retry_job", selection=[flaky_retry_asset])


# Fan-out: 3 independent assets (no shared dependency between them) sleeping
# briefly and logging start/end timestamps — the point is proving they
# actually overlap in time when materialized together, not just that all 3
# eventually finish. Each runs in its own step container (docker_executor),
# so this is genuine process-level parallelism, not just interleaved
# asyncio — the direct Dagster analog of Airflow's example_parallel_tasks
# and Temporal's BatchProcessingWorkflow (see docs/12-orchestration.md's
# feature-parity table).
def _fan_out_leaf(name: str) -> None:
    import time

    print(f"{name}: starting at {time.time():.2f}")
    time.sleep(5)
    print(f"{name}: finished at {time.time():.2f}")


@asset
def fan_out_a() -> None:
    _fan_out_leaf("fan_out_a")


@asset
def fan_out_b() -> None:
    _fan_out_leaf("fan_out_b")


@asset
def fan_out_c() -> None:
    _fan_out_leaf("fan_out_c")


fan_out_job = define_asset_job(name="fan_out_job", selection=[fan_out_a, fan_out_b, fan_out_c])


daily_partitions = DailyPartitionsDefinition(start_date="2026-08-01")


@asset(partitions_def=daily_partitions)
def daily_sales(context: AssetExecutionContext) -> dict:
    # Real version: query the source system for this specific date's data.
    # context.partition_key is that date ("2026-08-05", etc.) — Dagster
    # passes it in because this run was launched *for* that partition.
    date = context.partition_key
    return {"date": date, "sales_total": 1000 + (hash(date) % 500)}


# Backdated ingestion is materializing an old partition, not re-running the
# whole pipeline for a date range — that's the actual difference from
# Airflow's catchup/backfill (see docs/12-orchestration.md):
#   dagster asset materialize --select daily_sales --partition 2026-08-03
# A real range/backfill goes through the UI (Asset -> Partitions tab ->
# select a range -> Materialize) or `dagster asset materialize
# --partition-range 2026-08-01...2026-08-05`.


@asset(partitions_def=daily_partitions, backfill_policy=BackfillPolicy.single_run())
def daily_sales_single_run(context: AssetExecutionContext) -> None:
    # Same shape as daily_sales above, one crucial difference:
    # backfill_policy=BackfillPolicy.single_run() means backfilling a
    # *range* of partitions launches exactly one run (one step container)
    # that processes the whole range itself via context.partition_keys —
    # not one run per partition the way daily_sales's default backfill
    # policy does. Real fit: a source system where fetching 5 days in one
    # query is cheaper than 5 separate queries, or a downstream system
    # that only accepts bulk writes.
    #
    # Return type is None, not dict: a real gotcha hit building this — the
    # default filesystem IO manager can't persist one output covering
    # multiple partitions ("does not support persisting an output
    # associated with multiple partitions"), only one file path per
    # partition. Dagster's own error message suggests exactly this fix
    # (opt out of the IO manager by returning None) as the alternative to
    # writing a custom IO manager that does support multi-partition
    # outputs.
    keys = context.partition_keys
    totals = {d: 1000 + (hash(d) % 500) for d in keys}
    print(f"daily_sales_single_run processed {len(keys)} partitions in one run: {totals}")


class SourceSystemResource(ConfigurableResource):
    """A connection to an external source system. base_url is configuration
    (set once, below, in Definitions(resources=...)) — swap it per
    environment without touching the asset that uses it."""

    base_url: str = "https://example-source-system.internal"

    def fetch_record_count(self, table: str) -> int:
        # Real version: an actual HTTP/DB call against self.base_url.
        # Stubbed here so the example runs with no external dependency.
        return {"orders": 142, "customers": 58}.get(table, 0)


@asset
def source_system_summary(source_system: SourceSystemResource) -> dict:
    # `source_system` matches a *resource* key in Definitions(resources=...)
    # below, not another asset's name — Dagster checks the resources dict
    # first, so this parameter is a dependency injection, not a lineage edge.
    return {
        "orders": source_system.fetch_record_count("orders"),
        "customers": source_system.fetch_record_count("customers"),
    }


@multi_asset(
    outs={
        "orders_raw": AssetOut(),
        "orders_staged": AssetOut(),
        "orders_final": AssetOut(),
    }
)
def orders_multi_asset(context: AssetExecutionContext):
    # Real version: one API/DB round trip, then transform the result in
    # memory. This is the actual point of @multi_asset over three separate
    # @asset functions — raw/staged/final never leave this function until
    # they're each individually recorded as their own asset, no IO manager
    # hop needed between them the way cleaned_data depends on raw_data above.
    raw = [{"id": 1, "status": "new"}, {"id": 2, "status": "shipped"}, {"id": 3, "status": "cancelled"}]
    staged = [o for o in raw if o["status"] != "cancelled"]
    final = {"order_count": len(staged)}
    return raw, staged, final


@asset(
    description="Order records pulled from the source system, one row per order.",
    owners=["team:data-eng"],
    kinds={"postgres"},
)
def customer_orders() -> Output[list[dict]]:
    # Real version: read from the actual orders table. Stubbed the same way
    # as raw_data() above; the point here isn't the data, it's everything
    # attached to it below.
    rows = [
        {"order_id": 1, "customer_email": "a@example.com", "amount": 42.50, "status": "shipped"},
        {"order_id": 2, "customer_email": "b@example.com", "amount": 15.00, "status": "pending"},
        {"order_id": 3, "customer_email": "c@example.com", "amount": 99.99, "status": "shipped"},
    ]

    # Static description/owners/kinds above are fixed at definition time.
    # This metadata is computed fresh on every materialization instead —
    # shows up on this specific run, not just the asset in the abstract.
    return Output(
        rows,
        metadata={
            "row_count": MetadataValue.int(len(rows)),
            "preview": MetadataValue.md(
                "\n".join(
                    ["| order_id | customer_email | amount | status |", "| --- | --- | --- | --- |"]
                    + [f"| {r['order_id']} | {r['customer_email']} | {r['amount']} | {r['status']} |" for r in rows]
                )
            ),
            # Renders as a real column-by-column table on the asset's own UI
            # page — name/type/description per column, not just prose.
            "column_schema": MetadataValue.table_schema(
                TableSchema(
                    columns=[
                        TableColumn("order_id", "int", description="Primary key"),
                        TableColumn("customer_email", "string"),
                        TableColumn("amount", "float", description="Order total, USD"),
                        TableColumn("status", "string", description="pending | shipped | cancelled"),
                    ]
                )
            ),
        },
    )


@op
def extract_numbers() -> list[int]:
    # Real version: read from a file, queue, or API. Deliberately the same
    # kind of stub as raw_data() above, so the asset vs. op styles are easy
    # to compare side by side.
    return [4, 8, 15, 16, 23, 42]


@op
def total_numbers(numbers: list[int]) -> int:
    return sum(numbers)


@op
def print_total(total: int) -> None:
    print(f"ops_pipeline_job total: {total}")


@success_hook(required_resource_keys=set())
def log_job_success(context: HookContext) -> None:
    # Real version: post to ntfy/Slack, same real-world job as Airflow's
    # on_success_callback (see example_all_options.py's reference) and a
    # custom Notifier (example_custom_notifier.py) — Dagster's own version
    # of "run this when a step/job finishes," attached declaratively via
    # @job(hooks=...) below instead of passed as a callback argument.
    print(f"HOOK: {context.op.name} succeeded in job {context.job_name}")


@job(hooks={log_job_success})
def ops_pipeline_job():
    # Explicit function-call wiring, not inferred from a parameter name —
    # this is the entire difference from the asset examples above. Compare
    # against raw_data -> cleaned_data -> report: same 3-step shape, two
    # different ways of declaring the same dependency.
    print_total(total_numbers(extract_numbers()))


@sensor(job=report_job, minimum_interval_seconds=15)
def marker_file_sensor(context: SensorEvaluationContext):
    # Same self-contained pattern as Airflow's example_sensor.py (a marker
    # file, not a pre-configured connection) — reacts to an external event
    # instead of running on a fixed schedule, Dagster's parallel to
    # Airflow's Sensor concept.
    marker = Path("/tmp/io_manager_storage/.dagster_sensor_trigger")
    if not marker.exists():
        return SkipReason("Marker file not present yet.")
    marker.unlink()
    return RunRequest(run_key=f"marker-{context.cursor or '0'}")


# Dynamic partitions: unlike daily_sales's fixed DailyPartitionsDefinition
# (every partition known in advance, one per calendar day forever),
# uploaded_files_partitions starts with *zero* partitions — new ones are
# added at runtime, by name, as files actually show up. Tracked in
# Dagster's own metadata DB (get_dynamic_partitions/add_dynamic_partitions
# below), not in-memory, so this survives dagster-daemon restarting.
uploaded_files_partitions = DynamicPartitionsDefinition(name="uploaded_files")


@asset(partitions_def=uploaded_files_partitions)
def process_uploaded_file(context: AssetExecutionContext) -> str:
    # Real version: process the actual file named by this partition key.
    filename = context.partition_key
    return f"processed {filename}"


process_uploaded_file_job = define_asset_job(name="process_uploaded_file_job", selection=[process_uploaded_file])


@sensor(job=process_uploaded_file_job, minimum_interval_seconds=15)
def new_file_sensor(context: SensorEvaluationContext):
    watch_dir = Path("/tmp/io_manager_storage/.dynamic_partition_uploads")
    watch_dir.mkdir(exist_ok=True, parents=True)
    existing = set(context.instance.get_dynamic_partitions("uploaded_files"))
    new_files = sorted(f.name for f in watch_dir.iterdir() if f.is_file() and f.name not in existing)
    if not new_files:
        return SkipReason("No new files.")
    # This is the actual point: a brand-new partition key, created here,
    # at sensor-evaluation time — not declared anywhere in this file ahead
    # of time the way daily_sales's dates are.
    context.instance.add_dynamic_partitions("uploaded_files", new_files)
    return [RunRequest(partition_key=f, run_key=f"upload-{f}") for f in new_files]


# Reference, not a pattern demo like everything above: every @asset/@op/
# @job/ScheduleDefinition/@sensor option in one place, each shown at its
# real default with a one-line explanation — a checklist to copy from, not
# a live example of any one pattern. A handful are set for real below;
# everything else is commented-out. Captured via inspect.signature()
# against this image's pinned Dagster version — the source of truth if
# this ever drifts from a future Dagster version.
@asset(
    # --- commonly set ---
    description="Reference asset: every @asset option, real defaults documented inline.",
    # --- everything below: commented out, shown at its real default ---
    # name=None,                    # asset name — defaults to the function name
    # key_prefix=None,              # namespace the asset key, e.g. ["raw", "reference_asset"] — shows as a folder in the UI's asset graph
    # ins=None,                     # explicit AssetIn mapping when a parameter name can't/shouldn't match the upstream asset's own name
    # deps=None,                    # extra upstream dependencies that aren't function parameters (no data passed, just ordering)
    # metadata=None,                # static key/value metadata shown on the asset's own UI page — see customer_orders above for the computed-per-run alternative
    # tags=None,                    # freeform key/value tags for filtering/grouping in the UI
    # config_schema=None,           # a Config schema — makes this asset accept structured run-time config (Launchpad "Config" tab)
    # required_resource_keys=None,  # explicit resource-key set when a resource isn't picked up via a type-hinted parameter (see source_system_summary above for that style)
    # resource_defs=None,           # per-asset resource overrides — rare; usually resources are set once in Definitions(resources=...) below
    # hooks=None,                   # HookDefinitions (on_success/on_failure callbacks) attached directly to this asset
    # io_manager_def=None,          # inline IO manager just for this asset, instead of io_manager_key below pointing at a shared one
    # io_manager_key=None,          # which Definitions(resources=...) IO manager stores this asset's output — None = the default one (FilesystemIOManager below)
    # dagster_type=None,            # explicit DagsterType for the return value, beyond what a plain Python type hint already infers
    # partitions_def=None,          # e.g. DailyPartitionsDefinition — see daily_sales above for a real one
    # op_tags=None,                 # tags on the underlying Op specifically, distinct from the asset-level tags above
    # group_name=None,              # groups this asset under a named section in the UI's asset graph (default group is "default")
    # output_required=True,         # False = this asset is allowed to not yield an output on some runs (conditional materialization) without Dagster treating that as a failure
    # automation_condition=None,    # Declarative Automation — see report_notification above for AutomationCondition.eager() actually wired up
    # freshness_policy=None,        # declare how stale this asset is allowed to get before the UI flags it — a data-quality signal, not a hard blocker
    # backfill_policy=None,         # BackfillPolicy.single_run() vs. the default (one run per partition) — only relevant alongside partitions_def
    # retry_policy=None,            # RetryPolicy(max_retries=1, delay=None, backoff=None, jitter=None) — see reference_op below for the same concept on the @op side
    # code_version=None,            # a version string Dagster compares run-to-run to flag "this asset's *logic* changed since it last materialized," independent of the data itself
    # key=None,                     # fully explicit AssetKey, overriding name/key_prefix entirely
    # check_specs=None,             # declare AssetCheckSpecs inline instead of a separate @asset_check function (see report_freshness_check above for that style)
    # owners=None,                  # e.g. ["team:data-eng"] — see customer_orders above for a real one
    # kinds=None,                   # e.g. {"postgres"} — technology tags shown as small icons on the asset in the UI
    # pool=None,                    # named concurrency pool limiting how many ops/assets using this pool run at once cluster-wide — same concept as Airflow's Pool
)
def reference_asset() -> str:
    return "This asset exists to document options, not to do real work."


@op(
    # --- commonly set ---
    description="Reference op: every @op option, real defaults documented inline.",
    # --- everything below: commented out, shown at its real default ---
    # name=None,                    # op name — defaults to the function name
    # ins=None,                     # explicit In() mapping for this op's inputs — the @op equivalent of @asset's `ins`
    # out=None,                     # explicit Out() for this op's output(s) — description/metadata/io_manager_key on the output itself
    # config_schema=None,           # same Config-schema concept as @asset above
    # required_resource_keys=None,  # same resource-key concept as @asset above
    # tags=None,                    # freeform key/value tags for filtering/grouping in the UI
    # version=None,                 # deprecated alias for code_version below — use code_version in new code
    # retry_policy=RetryPolicy(max_retries=1, delay=None, backoff=None, jitter=None),  # active default shown explicitly — max_retries=1 means Dagster retries a failed op once before giving up; delay/backoff/jitter tune the wait between attempts (Backoff.LINEAR/EXPONENTIAL, Jitter.FULL/PLUS_MINUS)
    # code_version=None,            # same "did the logic change" version string as @asset's code_version above
    # pool=None,                    # same named concurrency pool as @asset's pool above
)
def reference_op() -> str:
    return "This op exists to document options, not to do real work."


@job(
    # --- commonly set ---
    description="Reference job: every @job option, real defaults documented inline.",
    # --- everything below: commented out, shown at its real default ---
    # name=None,                    # job name — defaults to the function name
    # resource_defs=None,           # per-job resource overrides — rare; usually resources are set once in Definitions(resources=...) below
    # config=None,                  # default run config for every launch of this job (a dict, RunConfig, or PartitionedConfig)
    # tags=None,                    # freeform key/value tags shown on every run of this job
    # run_tags=None,                # tags applied to the Dagster Run specifically (distinct from the job-definition tags above)
    # metadata=None,                # static key/value metadata shown on the job's own UI page
    # logger_defs=None,             # custom LoggerDefinitions available to ops in this job, beyond the default console logger
    # executor_def=None,            # override which Executor runs this one job — None = the Definitions(executor=...) default (docker_executor below)
    # hooks=None,                   # HookDefinitions attached to every op in this job
    # op_retry_policy=None,         # a RetryPolicy applied to every op in this job that doesn't set its own — same RetryPolicy shape as reference_op's above
    # partitions_def=None,          # partition this whole job the way daily_sales partitions a single asset
    # input_values=None,            # hardcoded input values for this job's root inputs, bypassing config entirely
    # owners=None,                  # e.g. ["team:data-eng"] — same concept as @asset's owners above
)
def reference_job():
    reference_op()


reference_schedule = ScheduleDefinition(
    # --- commonly set ---
    name="reference_schedule",
    cron_schedule="0 0 * * *",  # required if execution_fn isn't set — standard 5-field cron
    job=reference_job,
    description="Reference schedule: every ScheduleDefinition option, real defaults documented inline.",
    default_status=DefaultScheduleStatus.STOPPED,  # real default — every schedule starts off; flip it on from the Schedules tab (or DefaultScheduleStatus.RUNNING to start it enabled)
    # --- everything below: commented out, shown at its real default ---
    # job_name=None,                # target a job by name string instead of passing the job object directly via `job` above
    # run_config=None,              # static run config applied to every scheduled run
    # run_config_fn=None,           # compute run config dynamically from a ScheduleEvaluationContext instead of a static run_config
    # tags=None,                    # static tags applied to every scheduled run
    # tags_fn=None,                 # compute tags dynamically from a ScheduleEvaluationContext
    # metadata=None,                # static key/value metadata shown on the schedule's own UI page
    # should_execute=None,          # callable(context) -> bool — skip a tick entirely without even creating a (skipped) run
    # environment_vars=None,        # env vars available specifically to should_execute/run_config_fn/tags_fn at evaluation time
    # execution_timezone=None,      # IANA timezone for interpreting cron_schedule — None = UTC
    # execution_fn=None,            # full custom scheduling logic in place of a plain cron_schedule — rare, most schedules just need cron_schedule
    # required_resource_keys=None,  # resource keys needed by should_execute/run_config_fn/tags_fn specifically
    # target=None,                  # target an AssetSelection instead of a whole job — schedule a subset of assets directly
    # owners=None,                  # e.g. ["team:data-eng"] — same concept as @asset's owners above
)


@sensor(
    # --- commonly set ---
    name="reference_sensor",
    job=reference_job,
    description="Reference sensor: every @sensor option, real defaults documented inline.",
    default_status=DefaultSensorStatus.STOPPED,  # real default — every sensor starts off; flip it on from the Sensors tab (or DefaultSensorStatus.RUNNING to start it enabled)
    # --- everything below: commented out, shown at its real default ---
    # job_name=None,                # target a job by name string instead of the positional job_name/job kwarg above
    # minimum_interval_seconds=None,  # floor on how often dagster-daemon evaluates this sensor — None = daemon's own default cadence (~30s)
    # jobs=None,                    # target several jobs at once instead of one via `job` above — each RunRequest picks which one it's for
    # asset_selection=None,         # target specific assets directly instead of a whole job — the sensor equivalent of ScheduleDefinition's `target` above
    # required_resource_keys=None,  # resource keys needed inside the sensor function itself
    # tags=None,                    # static tags applied to every run this sensor requests
    # metadata=None,                # static key/value metadata shown on the sensor's own UI page
    # target=None,                  # same AssetSelection-targeting concept as ScheduleDefinition's `target` above
    # owners=None,                  # e.g. ["team:data-eng"] — same concept as @asset's owners above
)
def reference_sensor(context: SensorEvaluationContext):
    # Always skips — this sensor exists to document @sensor's options, not
    # to actually fire. Compare marker_file_sensor above for a real one.
    return SkipReason("reference_sensor never fires — it exists to document @sensor's options, not to run.")


defs = Definitions(
    assets=[
        hello_homeserver,
        raw_data,
        cleaned_data,
        report,
        report_notification,
        daily_sales,
        source_system_summary,
        orders_multi_asset,
        customer_orders,
        reference_asset,
        flaky_retry_asset,
        fan_out_a,
        fan_out_b,
        fan_out_c,
        daily_sales_single_run,
        process_uploaded_file,
    ],
    asset_checks=[report_freshness_check],
    jobs=[ops_pipeline_job, reference_job, flaky_retry_job, fan_out_job, process_uploaded_file_job],
    schedules=[report_daily_schedule, reference_schedule],
    sensors=[marker_file_sensor, reference_sensor, new_file_sensor],
    # Every step runs in its own ephemeral container (a fresh filesystem each
    # time) — the default IO manager's per-run temp dir isn't shared between
    # them, so cleaned_data can't see raw_data's output unless both point at
    # the same *mounted* path. io_manager_storage (declared in compose.yml,
    # mounted here AND into every step container via container_kwargs.volumes
    # below) is that shared path.
    resources={
        "io_manager": FilesystemIOManager(base_dir="/tmp/io_manager_storage"),
        "source_system": SourceSystemResource(),
    },
    executor=docker_executor.configured(
        {
            "network": "homeserver",
            "container_kwargs": {
                "mem_limit": "512m",
                "nano_cpus": 1_000_000_000,  # 1 CPU — raise if a real asset needs more
                # Step containers use the same homeserver/dagster-user-code
                # image, which no longer bakes in definitions.py — needs this
                # mount too, or a step can't import the code it's supposed to
                # run. Hardcoded absolute host path, not ${DATA_ROOT}/... —
                # this file is baked into the image at build time, not
                # compose-interpolated. Update if service_data/ ever moves.
                "volumes": [
                    "dagster-io-manager-storage:/tmp/io_manager_storage",
                    "/mnt/mydata/homeserver/service_data/data/dagster/user-code:/opt/dagster/app",
                ],
                "auto_remove": True,
            },
        }
    ),
)
