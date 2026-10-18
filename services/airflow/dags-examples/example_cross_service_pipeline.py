"""Starter example — the capstone: Airflow schedules, Temporal durably
orchestrates, Dagster materializes assets with lineage. Each tool doing the
one thing it's actually best at, instead of picking just one and stretching
it to cover everything.

This task starts Temporal's MaterializeDagsterAssetWorkflow and waits for
it to finish. That workflow (services/temporal/worker/workflows.py) calls
Dagster's GraphQL API to launch report_job and polls until it completes —
durably: if the Temporal worker crashes mid-poll, Temporal replays and keeps
waiting, no state lost. This DAG doesn't know or care about that — it just
sees one task that eventually succeeds or fails.
"""

import asyncio
from datetime import datetime

from airflow.sdk import dag, task


@dag(
    dag_id="example_cross_service_pipeline",
    description="Starter example: Airflow schedules a durable Temporal workflow that materializes a Dagster asset",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example", "cross-service"],
)
def example_cross_service_pipeline():
    @task
    def trigger_dagster_materialization_via_temporal() -> str:
        import os

        from temporalio.client import Client
        from temporalio.envconfig import ClientConfig

        async def _run() -> str:
            # Temporal's standard environment configuration, as the worker uses
            # (TEMPORAL_ADDRESS, TEMPORAL_API_KEY, TEMPORAL_TLS*, ...): Temporal
            # Cloud is an .env change, never a code change.
            config = ClientConfig.load_client_connect_config()
            if not config.get("api_key"):  # empty key = none (self-hosted, plain text)
                config.pop("api_key", None)
                if config.get("tls") is True and "TEMPORAL_TLS" not in os.environ:
                    config.pop("tls")
            client = await Client.connect(**config)
            return await client.execute_workflow(
                "MaterializeDagsterAssetWorkflow",
                "report_job",
                id=f"airflow-triggered-{datetime.now():%Y%m%d%H%M%S}",
                task_queue="homeserver",
            )

        return asyncio.run(_run())

    trigger_dagster_materialization_via_temporal()


example_cross_service_pipeline()
