"""Placeholder Temporal worker — replace with real workflow/activity code.

Starter workflows, each demonstrating a different Temporal strength — see
workflows.py's docstrings and docs/services/temporal/temporal.md for how to run each
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
    reference_activity,
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
    ReferenceWorkflow,
    RetryableActivityWorkflow,
    RunContainerWorkflow,
)

TASK_QUEUE = "homeserver"

# Same task queue *name* in different Namespaces is a completely separate
# queue each time — a Namespace is the isolation boundary, not the queue
# name. One worker process here runs one Worker loop per Namespace,
# concurrently, all polling "homeserver" — proves it: start the same
# Workflow ID in two or more of these (see docs/services/temporal/temporal.md) and
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
    ReferenceWorkflow,
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
    reference_activity,
]


async def run_worker(namespace: str) -> None:
    client = await Client.connect("temporal:7233", namespace=namespace)
    # Worker(...)'s own options, real defaults — process-wide, so they apply
    # to every workflow/activity above, not to any one of them. Captured via
    # inspect.signature() against this repo's pinned temporalio version (see
    # services/temporal/worker/pyproject.toml); the handful actually used in
    # a homelab-scale deployment are set for real below, everything else is
    # a checklist — most of it (tuner, deployment_config, interceptors...)
    # is for large multi-worker fleets, not a single worker like this one.
    #   Worker(
    #       client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=ACTIVITIES,
    #       activity_executor=None,                # thread/process pool for *synchronous* activities — required if any activity isn't `async def`; none here are
    #       max_cached_workflows=1000,              # sticky-cache size — how many workflow executions stay warm in memory between tasks
    #       max_concurrent_workflow_tasks=None,     # cap concurrent workflow-task processing — None = SDK-chosen default
    #       max_concurrent_activities=None,         # cap concurrent activity executions on this worker — the actual throughput/resource knob most homelab tuning wants
    #       max_concurrent_local_activities=None,   # same, for local activities (execute_local_activity — none used in this repo's workflows)
    #       graceful_shutdown_timeout=timedelta(0), # how long to let in-flight activities finish before SIGTERM force-kills them — 0 = immediate
    #       max_activities_per_second=None,         # global rate limit across all activities on this worker
    #       max_task_queue_activities_per_second=None,  # rate limit for this Task Queue specifically (server-side, shared across all workers polling it)
    #       identity=None,                          # worker identity string shown in the UI's Event History — defaults to a generated one
    #       build_id=None,                          # deprecated — superseded by Worker Versioning (use_worker_versioning/deployment_config)
    #       debug_mode=False,                       # True = disable workflow sandboxing's timeout enforcement, for stepping through with a debugger
    #       workflow_task_poller_behavior=PollerBehaviorSimpleMaximum(maximum=5),  # how many pollers this worker runs for workflow tasks
    #       activity_task_poller_behavior=PollerBehaviorSimpleMaximum(maximum=5), # same, for activity tasks
    #   )
    worker = Worker(client, task_queue=TASK_QUEUE, workflows=WORKFLOWS, activities=ACTIVITIES)
    await worker.run()


async def main() -> None:
    await asyncio.gather(*(run_worker(ns) for ns in NAMESPACES))


if __name__ == "__main__":
    asyncio.run(main())
