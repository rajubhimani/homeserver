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
"""

from pathlib import Path

from dagster import (
    AssetCheckResult,
    AssetExecutionContext,
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
    assets=[hello_homeserver, raw_data, cleaned_data, report, daily_sales],
    asset_checks=[report_freshness_check],
    schedules=[report_daily_schedule],
    sensors=[marker_file_sensor],
    # Every step runs in its own ephemeral container (a fresh filesystem each
    # time) — the default IO manager's per-run temp dir isn't shared between
    # them, so cleaned_data can't see raw_data's output unless both point at
    # the same *mounted* path. io_manager_storage (declared in compose.yml,
    # mounted here AND into every step container via container_kwargs.volumes
    # below) is that shared path.
    resources={"io_manager": FilesystemIOManager(base_dir="/tmp/io_manager_storage")},
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
