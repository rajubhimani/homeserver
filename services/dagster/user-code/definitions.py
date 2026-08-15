"""Starter pipeline — replace with your own assets/jobs/schedules.

Things this is meant to show a new user:
1. hello_homeserver: the simplest possible asset.
2. raw_data -> cleaned_data -> report: Dagster's actual strength — assets
   are data, not steps. Dependencies are inferred from function parameter
   names (cleaned_data's `raw_data` argument IS the dependency declaration —
   no >> operator, no manual DAG wiring), and every materialization is
   automatically resource-bounded via docker_executor below, the same
   pattern as Airflow's DockerOperator and Temporal's worker (see
   docs/services/dagster.md and the other two services' docs).
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
"""

from pathlib import Path

from dagster import (
    AssetCheckResult,
    AssetExecutionContext,
    AssetOut,
    AutomationCondition,
    ConfigurableResource,
    DailyPartitionsDefinition,
    Definitions,
    FilesystemIOManager,
    RunRequest,
    ScheduleDefinition,
    SensorEvaluationContext,
    SkipReason,
    asset,
    asset_check,
    define_asset_job,
    job,
    multi_asset,
    op,
    sensor,
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


@job
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
    ],
    asset_checks=[report_freshness_check],
    jobs=[ops_pipeline_job],
    schedules=[report_daily_schedule],
    sensors=[marker_file_sensor],
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
