"""Placeholder Temporal worker — replace with real workflow/activity code.

Five starter workflows, each demonstrating a different Temporal strength —
see workflows.py's docstrings and docs/services/temporal.md for how to run
each one from temporal-admin-tools.
"""

import asyncio

from temporalio.client import Client
from temporalio.worker import Worker

from activities import (
    charge_payment_activity,
    create_shipment_activity,
    flaky_activity,
    materialize_dagster_asset_activity,
    refund_payment_activity,
    release_inventory_activity,
    reserve_inventory_activity,
    run_container_activity,
)
from workflows import (
    ApprovalWorkflow,
    MaterializeDagsterAssetWorkflow,
    OrderFulfillmentSagaWorkflow,
    RetryableActivityWorkflow,
    RunContainerWorkflow,
)

TASK_QUEUE = "homeserver"


async def main() -> None:
    client = await Client.connect("temporal:7233")
    worker = Worker(
        client,
        task_queue=TASK_QUEUE,
        workflows=[
            RunContainerWorkflow,
            RetryableActivityWorkflow,
            ApprovalWorkflow,
            MaterializeDagsterAssetWorkflow,
            OrderFulfillmentSagaWorkflow,
        ],
        activities=[
            run_container_activity,
            flaky_activity,
            materialize_dagster_asset_activity,
            reserve_inventory_activity,
            release_inventory_activity,
            charge_payment_activity,
            refund_payment_activity,
            create_shipment_activity,
        ],
    )
    await worker.run()


if __name__ == "__main__":
    asyncio.run(main())
