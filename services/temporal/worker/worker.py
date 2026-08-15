"""Placeholder Temporal worker — replace with real workflow/activity code.

Starter workflows, each demonstrating a different Temporal strength — see
workflows.py's docstrings and docs/services/temporal.md for how to run each
one from temporal-admin-tools.
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
    BatchProcessingWorkflow,
    ConfigurableCounterWorkflow,
    DelayedReminderWorkflow,
    GreetSourceWorkflow,
    MaterializeDagsterAssetWorkflow,
    OrderFulfillmentSagaWorkflow,
    RecurringPollWorkflow,
    RetryableActivityWorkflow,
    RunContainerWorkflow,
)

TASK_QUEUE = "homeserver"

# Same task queue *name* in different Namespaces is a completely separate
# queue each time — a Namespace is the isolation boundary, not the queue
# name. One worker process here runs one Worker loop per Namespace,
# concurrently, all polling "homeserver" — proves it: start the same
# Workflow ID in two or more of these (see docs/services/temporal.md) and
# they run as fully independent executions with zero shared state or
# history. "staging"/"production" here are a real, common reason to reach
# for multiple Namespaces on one cluster: environment isolation without
# standing up a second Temporal deployment.
NAMESPACES = ["default", "staging", "production"]

WORKFLOWS = [
    RunContainerWorkflow,
    RetryableActivityWorkflow,
    ApprovalWorkflow,
    MaterializeDagsterAssetWorkflow,
    OrderFulfillmentSagaWorkflow,
    GreetSourceWorkflow,
    BatchProcessingWorkflow,
    DelayedReminderWorkflow,
    ConfigurableCounterWorkflow,
    RecurringPollWorkflow,
]

ACTIVITIES = [
    run_container_activity,
    flaky_activity,
    materialize_dagster_asset_activity,
    reserve_inventory_activity,
    release_inventory_activity,
    charge_payment_activity,
    refund_payment_activity,
    create_shipment_activity,
]


async def run_worker(namespace: str) -> None:
    client = await Client.connect("temporal:7233", namespace=namespace)
    worker = Worker(client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=ACTIVITIES)
    await worker.run()


async def main() -> None:
    await asyncio.gather(*(run_worker(ns) for ns in NAMESPACES))


if __name__ == "__main__":
    asyncio.run(main())
