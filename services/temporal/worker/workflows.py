"""Workflow definitions — imports the Activity through Temporal's sandbox
pass-through, since the Activity's own module (activities.py) imports
`docker`, which the deterministic workflow sandbox would otherwise reject."""

from datetime import timedelta

from temporalio import workflow
from temporalio.common import RetryPolicy
from temporalio.exceptions import ApplicationError

with workflow.unsafe.imports_passed_through():
    from activities import (
        RunContainerInput,
        charge_payment_activity,
        create_shipment_activity,
        flaky_activity,
        materialize_dagster_asset_activity,
        refund_payment_activity,
        release_inventory_activity,
        reserve_inventory_activity,
        run_container_activity,
    )


@workflow.defn
class RunContainerWorkflow:
    """Strength: resource-bounded execution — every step can run as its own
    container with explicit mem/CPU limits (see docs/services/temporal.md)."""

    @workflow.run
    async def run(self, inp: RunContainerInput) -> str:
        return await workflow.execute_activity(
            run_container_activity,
            inp,
            start_to_close_timeout=timedelta(minutes=5),
        )


@workflow.defn
class RetryableActivityWorkflow:
    """Strength: durability — Temporal retries a failing Activity on its own,
    with real backoff, and the Workflow code itself has zero retry logic to
    write or get wrong. flaky_activity fails twice, then succeeds on the 3rd
    call; watch it retry live in the UI's Event History."""

    @workflow.run
    async def run(self, call_id: str) -> str:
        return await workflow.execute_activity(
            flaky_activity,
            call_id,
            start_to_close_timeout=timedelta(seconds=10),
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),
                backoff_coefficient=2.0,
                maximum_attempts=5,
            ),
        )


@workflow.defn
class ApprovalWorkflow:
    """Strength: durable state across arbitrarily long waits — this workflow
    can sit paused for months (surviving worker restarts/redeploys/crashes;
    Temporal replays its history rather than needing the process to stay
    alive) until a human calls the `approve` Signal from outside. A common
    real shape: "run this pipeline, but pause before the destructive step
    until someone clicks approve."

    Signal it via:
      docker exec -it temporal-admin-tools temporal workflow signal \\
        --address temporal:7233 --workflow-id <id> --name approve

    Query its state at any time — unlike a Signal, this doesn't affect
    execution, just reads current state, and works even after completion:
      docker exec -it temporal-admin-tools temporal workflow query \\
        --address temporal:7233 --workflow-id <id> --type status
    """

    def __init__(self) -> None:
        self._approved = False

    @workflow.signal
    def approve(self) -> None:
        self._approved = True

    @workflow.query
    def status(self) -> str:
        return "approved" if self._approved else "pending"

    @workflow.run
    async def run(self) -> str:
        await workflow.wait_condition(lambda: self._approved)
        return "approved — proceeding with the (real) next step"


@workflow.defn
class MaterializeDagsterAssetWorkflow:
    """Strength: cross-service architecture. Temporal durably coordinates a
    Dagster materialization it doesn't run itself — if this worker crashes
    mid-poll, Temporal replays and keeps waiting for the Dagster run with no
    state lost, something a plain script polling in a loop can't do. Airflow
    (example_cross_service_pipeline DAG) starts this on a schedule: Airflow
    schedules, Temporal durably orchestrates, Dagster materializes assets
    with lineage — each tool doing the one thing it's actually best at."""

    @workflow.run
    async def run(self, job_name: str = "report_job") -> str:
        return await workflow.execute_activity(
            materialize_dagster_asset_activity,
            job_name,
            start_to_close_timeout=timedelta(minutes=10),
            heartbeat_timeout=timedelta(seconds=30),
        )


@workflow.defn
class OrderFulfillmentSagaWorkflow:
    """Strength: the Saga pattern — Temporal's flagship real-world use case
    (Uber ride dispatch/driver payouts, Netflix billing retries, Amazon
    multi-warehouse fulfillment all run this shape at scale). A distributed
    transaction across services (inventory, payment, shipping), written as
    plain sequential code with try/except for compensation — no separate
    saga-definition DSL, no manually tracking which steps already committed.

    Reserve inventory -> charge payment -> create shipment. If payment or
    shipping fails partway through, the already-completed steps are undone
    in reverse order (release inventory, refund payment) so the system never
    ends up in a half-committed state. amount > 1000 simulates a declined
    payment, so both the happy path and the compensation path are real,
    runnable outcomes, not just described:

      docker exec -it temporal-admin-tools temporal workflow start --address temporal:7233 \\
        --task-queue homeserver --type OrderFulfillmentSagaWorkflow \\
        --input '{"order_id": "ord-1", "amount": 50}'      # succeeds
      docker exec -it temporal-admin-tools temporal workflow start --address temporal:7233 \\
        --task-queue homeserver --type OrderFulfillmentSagaWorkflow \\
        --input '{"order_id": "ord-2", "amount": 5000}'    # payment declined -> compensates
    """

    @workflow.run
    async def run(self, order: dict) -> str:
        order_id, amount = order["order_id"], order["amount"]
        timeout = timedelta(seconds=30)

        await workflow.execute_activity(reserve_inventory_activity, order_id, start_to_close_timeout=timeout)

        try:
            await workflow.execute_activity(
                charge_payment_activity, {"order_id": order_id, "amount": amount}, start_to_close_timeout=timeout
            )
        except Exception as e:
            await workflow.execute_activity(release_inventory_activity, order_id, start_to_close_timeout=timeout)
            raise ApplicationError(f"Order {order_id} failed at payment, compensated: {e}") from e

        try:
            await workflow.execute_activity(create_shipment_activity, order_id, start_to_close_timeout=timeout)
        except Exception as e:
            await workflow.execute_activity(
                refund_payment_activity, {"order_id": order_id, "amount": amount}, start_to_close_timeout=timeout
            )
            await workflow.execute_activity(release_inventory_activity, order_id, start_to_close_timeout=timeout)
            raise ApplicationError(f"Order {order_id} failed at shipping, compensated: {e}") from e

        return f"Order {order_id} fulfilled: inventory reserved, payment charged, shipment created"
