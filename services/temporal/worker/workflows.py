"""Workflow definitions — imports the Activity through Temporal's sandbox
pass-through, since the Activity's own module (activities.py) imports
`docker`, which the deterministic workflow sandbox would otherwise reject."""

import asyncio
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
        reference_activity,
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
class GreetSourceWorkflow:
    """Child workflow for BatchProcessingWorkflow below — small and
    self-contained on purpose, since the point of this pair is the
    parent/child relationship, not what the child itself computes."""

    @workflow.run
    async def run(self, source_name: str) -> str:
        return f"processed {source_name}"


@workflow.defn
class BatchProcessingWorkflow:
    """Strength: composition — a parent workflow durably coordinating
    multiple independent child workflows. Each child gets its own Workflow
    ID and its own Event History; one child failing doesn't corrupt another
    child's state or the parent's. Runs children concurrently via
    asyncio.gather + execute_child_workflow (Temporal's deterministic
    asyncio event loop makes this safe, unlike a raw thread pool).

    Compare to Airflow's example_parallel_tasks.py fan-out: same shape at a
    glance, but each child here is independently durable and independently
    queryable/signalable — not just a step scheduled inside one DAG run."""

    @workflow.run
    async def run(self, sources: list[str]) -> list[str]:
        parent_id = workflow.info().workflow_id
        results = await asyncio.gather(
            *[
                workflow.execute_child_workflow(
                    GreetSourceWorkflow.run,
                    source,
                    id=f"{parent_id}-child-{source}",
                )
                for source in sources
            ]
        )
        return list(results)


@workflow.defn
class DelayedReminderWorkflow:
    """Strength: a durable timer. `asyncio.sleep()` inside a workflow *is*
    the durable timer — Temporal's deterministic asyncio event loop makes
    the same stdlib call replay-safe, unlike a plain script's asyncio.sleep
    which just blocks that one process. Kill the worker mid-sleep
    (`docker stop temporal-worker`) and bring it back up
    (`docker start temporal-worker`): the timer still fires at the original
    time, not delayed by however long the worker was down, because it's
    tracked by Temporal Server, not the worker process. Sleeping costs
    nothing while waiting — no polling loop, no cron job to keep alive — so
    the same call works unchanged for `timedelta(days=30)` as it does here
    for a few seconds."""

    @workflow.run
    async def run(self, delay_seconds: int = 5) -> str:
        await asyncio.sleep(delay_seconds)
        return f"Reminder fired after {delay_seconds}s durable sleep."


@workflow.defn
class ConfigurableCounterWorkflow:
    """Strength: Update — request/response messaging into a running
    workflow, the newer sibling of Signal for anything that needs the
    caller to get a value back or to know their change was accepted before
    moving on. A Signal is fire-and-forget; an Update blocks the caller
    until the handler returns, and a validator can reject the change before
    it's even written to Event History.

    Send an Update and read back the new count:
      docker exec -it temporal-admin-tools temporal workflow update execute \\
        --address temporal:7233 --workflow-id <id> --name increment --input 5

    A negative amount is rejected by the validator before it ever touches
    workflow state:
      docker exec -it temporal-admin-tools temporal workflow update execute \\
        --address temporal:7233 --workflow-id <id> --name increment --input -1

    Finish it (plain Signal, same pattern as ApprovalWorkflow above):
      docker exec -it temporal-admin-tools temporal workflow signal \\
        --address temporal:7233 --workflow-id <id> --name finish
    """

    def __init__(self) -> None:
        self._count = 0
        self._done = False

    @workflow.update
    def increment(self, amount: int) -> int:
        self._count += amount
        return self._count

    @increment.validator
    def _validate_increment(self, amount: int) -> None:
        if amount <= 0:
            raise ValueError("amount must be positive")

    @workflow.signal
    def finish(self) -> None:
        self._done = True

    @workflow.run
    async def run(self) -> int:
        await workflow.wait_condition(lambda: self._done)
        return self._count


@workflow.defn
class RecurringPollWorkflow:
    """Strength: Continue-As-New — Temporal's answer to "this workflow runs
    forever" (a recurring poll loop, a counter that never stops) without its
    Event History growing without bound. Every `ITERATIONS_PER_RUN` loops,
    it closes the current Run and starts a brand-new one under the *same*
    Workflow ID — same logical workflow, fresh empty History, indefinitely
    cheap. The WorkflowId stays constant across every Run; only the RunId
    changes — that's how "still the same workflow, just continued" is told
    apart from "a new workflow." Contrast with DelayedReminderWorkflow
    above: that one is durable but finite. This one is durable *and*
    unbounded.

    It never stops on its own — watch the RunId change, then terminate it:
      docker exec -it temporal-admin-tools temporal workflow start --address temporal:7233 \\
        --task-queue homeserver --type RecurringPollWorkflow --workflow-id poll-demo-1
      docker exec -it temporal-admin-tools temporal workflow describe --address temporal:7233 \\
        --workflow-id poll-demo-1   # RunId here changes every 3 polls — same WorkflowId throughout
      docker exec -it temporal-admin-tools temporal workflow terminate --address temporal:7233 \\
        --workflow-id poll-demo-1
    """

    ITERATIONS_PER_RUN = 3

    @workflow.run
    async def run(self, poll_count: int = 0) -> None:
        for _ in range(self.ITERATIONS_PER_RUN):
            poll_count += 1
            workflow.logger.info(f"poll #{poll_count}")
            await asyncio.sleep(2)

        workflow.continue_as_new(poll_count)


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


# @workflow.defn's own options, real defaults — commented since none of
# them need changing for this reference workflow to work:
#   @workflow.defn(
#       name=None,                  # Workflow Type name sent over the wire — defaults to the class name
#       sandboxed=True,             # False = skip the deterministic-import sandbox entirely for this workflow (rarely needed; costs you replay-safety guarantees)
#       dynamic=False,              # True = catch-all workflow invoked for any Workflow Type not otherwise registered on this worker
#       failure_exception_types=[], # exception types that fail the *workflow task* (retried forever) instead of just this run — advanced, see Temporal's Workflow Failure docs
#       versioning_behavior=VersioningBehavior.UNSPECIFIED,  # Worker Versioning (Worker Deployments) — irrelevant unless you've opted into that feature
#   )
@workflow.defn
class ReferenceWorkflow:
    """Reference, not a pattern demo like the workflows above: every
    `workflow.execute_activity()` and `RetryPolicy` option in one place,
    each shown at its real default with a one-line explanation — a
    checklist to copy from, not a live example of any one pattern. See
    `reference_activity` in activities.py, and `@activity.defn`'s own
    (much shorter) option list documented right above it there.

    Two things `execute_activity()` has no real default for and *requires*
    one of: `schedule_to_close_timeout` or `start_to_close_timeout` — pick
    at least one, or the call raises `TypeError` before ever reaching the
    server. `start_to_close_timeout` is set below since it's the one
    almost every real activity call actually wants (a per-attempt cap;
    `schedule_to_close_timeout` is the rarer end-to-end cap across every
    retry combined).

    Captured against `temporalio` (see `services/temporal/worker/pyproject.toml`
    for the pinned version) via `inspect.signature()` against
    `workflow.execute_activity`/`RetryPolicy.__init__`/`Worker.__init__` —
    the source of truth if this ever drifts from a future SDK version.
    `Worker.__init__`'s own process-wide options (concurrency limits, poller
    behavior, versioning...) are documented as a comment in `worker.py`
    itself, next to where this repo's one `Worker(...)` is actually
    constructed — those apply to the whole worker process, not to any one
    workflow, so they don't belong in a per-workflow reference like this.
    """

    @workflow.run
    async def run(self) -> str:
        return await workflow.execute_activity(
            # --- commonly set ---
            reference_activity,
            True,  # `arg` — the single positional input; use `args=[...]` instead for more than one
            start_to_close_timeout=timedelta(seconds=30),  # per-attempt cap — required (see docstring above)
            retry_policy=RetryPolicy(
                initial_interval=timedelta(seconds=1),  # wait before the *first* retry
                backoff_coefficient=2.0,  # multiply the wait by this each subsequent retry
                maximum_interval=None,  # cap on the wait between retries — real default is 100x initial_interval, not unbounded
                maximum_attempts=0,  # total attempts including the first — 0 means unlimited, retries forever until start_to_close_timeout/schedule_to_close_timeout gives up
                non_retryable_error_types=None,  # error class names that skip retry entirely — see charge_payment_activity's ApplicationError(non_retryable=True) above for the per-raise equivalent
            ),
            # --- everything below: commented out, shown at its real default ---
            # task_queue=None,                  # route this activity to a different Task Queue than the workflow's own — None = same queue
            # result_type=None,                 # explicit return-type hint for the SDK's deserializer — usually unneeded, inferred from the activity's own type hints
            # schedule_to_close_timeout=None,   # end-to-end cap across every retry combined — set this OR start_to_close_timeout (both is fine, whichever is tighter wins)
            # schedule_to_start_timeout=None,   # how long an activity may sit queued before a worker even picks it up — catches "no worker is listening" fast
            # heartbeat_timeout=None,           # required for a long activity to report liveness via activity.heartbeat() — see materialize_dagster_asset_activity above for a real one
            # cancellation_type=ActivityCancellationType.TRY_CANCEL,  # how workflow-side cancellation reaches this activity — TRY_CANCEL (default) / WAIT_CANCELLATION / ABANDON
            # activity_id=None,                 # explicit Activity ID instead of an auto-generated one — rarely needed
            # versioning_intent=None,           # Worker Versioning hint — irrelevant unless you've opted into that feature
            # summary=None,                     # short human-readable label shown in the UI's Event History, separate from the activity's actual input
            # priority=Priority(),               # Task Queue priority — higher-priority activities are dispatched first when a queue is backed up
        )
