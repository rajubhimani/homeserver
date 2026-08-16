"""Activities — the only file that imports `docker`. Kept separate from
workflows.py because Temporal's Python SDK sandboxes each workflow's own
module and rejects non-deterministic imports (docker -> http.client) even
when only the Activity actually uses them."""

import asyncio
import json
import urllib.request
from dataclasses import dataclass, field

import docker
from temporalio import activity
from temporalio.exceptions import ApplicationError


@dataclass
class RunContainerInput:
    image: str
    command: list[str] = field(default_factory=list)
    mem_limit: str = "128m"
    cpu_count: int = 1


@activity.defn
async def run_container_activity(inp: RunContainerInput) -> str:
    client = docker.from_env()
    output = client.containers.run(
        inp.image,
        command=inp.command or None,
        mem_limit=inp.mem_limit,
        cpu_count=inp.cpu_count,
        network="homeserver",
        remove=True,
    )
    return output.decode("utf-8", errors="replace") if isinstance(output, bytes) else str(output)


# In-memory counter so this activity actually fails the first two times it's
# called for a given workflow run, then succeeds on the third attempt — makes
# Temporal's automatic retry (configured on the workflow side, see
# workflows.py's RetryPolicy) visibly do something instead of just existing
# in a code sample nobody sees fire.
_attempt_counts: dict[str, int] = {}


@activity.defn
async def flaky_activity(call_id: str) -> str:
    _attempt_counts[call_id] = _attempt_counts.get(call_id, 0) + 1
    attempt = _attempt_counts[call_id]
    if attempt < 3:
        raise RuntimeError(f"simulated transient failure (attempt {attempt}/3)")
    return f"succeeded on attempt {attempt} — Temporal retried this automatically, no retry loop written by hand"


@activity.defn
async def materialize_dagster_asset_activity(job_name: str) -> str:
    """Cross-service orchestration: launches a Dagster job via its GraphQL
    API and polls until it finishes, heartbeating so Temporal knows this
    long-running activity is still alive (not stuck) — the same call
    docs/services/dagster/dagster.md's "Try the starter examples" section makes by
    hand with dagster-graphql, just driven durably from a workflow instead."""
    graphql_url = "http://dagster-webserver:3000/graphql"

    def _post(query: str, variables: dict) -> dict:
        payload = json.dumps({"query": query, "variables": variables}).encode()
        req = urllib.request.Request(
            graphql_url, data=payload, headers={"Content-Type": "application/json"}, method="POST"
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read())

    launch = _post(
        """
        mutation($jobName: String!) {
          launchPipelineExecution(executionParams: {
            selector: {repositoryLocationName: "user_code", repositoryName: "__repository__", pipelineName: $jobName}
            mode: "default"
          }) {
            __typename
            ... on LaunchRunSuccess { run { runId } }
            ... on PythonError { message }
          }
        }
        """,
        {"jobName": job_name},
    )["data"]["launchPipelineExecution"]
    if launch["__typename"] != "LaunchRunSuccess":
        raise RuntimeError(f"Dagster launch failed: {launch}")
    run_id = launch["run"]["runId"]

    for _ in range(60):  # ~5 minutes at 5s intervals
        activity.heartbeat(f"waiting on Dagster run {run_id}")
        status = _post(
            "query($id: ID!) { runOrError(runId: $id) { __typename ... on Run { status } } }",
            {"id": run_id},
        )["data"]["runOrError"].get("status")
        if status in ("SUCCESS", "FAILURE", "CANCELED"):
            if status != "SUCCESS":
                raise RuntimeError(f"Dagster run {run_id} ended with status {status}")
            return f"Dagster run {run_id} succeeded"
        await asyncio.sleep(5)

    raise TimeoutError(f"Dagster run {run_id} did not finish within the poll window")


# Saga pattern — Temporal's flagship use case (this is how Uber dispatches
# rides/driver payouts, Netflix handles subscription billing retries, Amazon
# does multi-warehouse order fulfillment: a distributed transaction across
# several services, with compensating actions to unwind whatever already
# succeeded if a later step fails). Real versions of these activities call
# actual Inventory/Payment/Shipping services; these just simulate one
# realistic failure (payment declined above a threshold) so both the
# happy path and the compensation path are actually exercised, not just
# described.


@activity.defn
async def reserve_inventory_activity(order_id: str) -> str:
    return f"Inventory reserved for order {order_id}"


@activity.defn
async def release_inventory_activity(order_id: str) -> str:
    return f"Inventory released for order {order_id} (compensation)"


@activity.defn
async def charge_payment_activity(inp: dict) -> str:
    order_id, amount = inp["order_id"], inp["amount"]
    if amount > 1000:
        # non_retryable=True: a declined payment is a business decision, not
        # a transient fault — Temporal's default policy retries activity
        # failures indefinitely, which would never let the workflow's
        # compensation logic run at all (confirmed live: without this, the
        # workflow just sits retrying charge_payment_activity forever
        # instead of releasing inventory).
        raise ApplicationError(
            f"Payment declined for order {order_id}: amount {amount} exceeds simulated limit of 1000",
            non_retryable=True,
        )
    return f"Charged {amount} for order {order_id}"


@activity.defn
async def refund_payment_activity(inp: dict) -> str:
    return f"Refunded {inp['amount']} for order {inp['order_id']} (compensation)"


@activity.defn
async def create_shipment_activity(order_id: str) -> str:
    return f"Shipment created for order {order_id}"


# @activity.defn's own options, real defaults — the decorator itself, not
# execute_activity() below which is how a *caller* invokes one:
#   @activity.defn(
#       name=None,                     # Activity Type name sent over the wire — defaults to the function name
#       no_thread_cancel_exception=False,  # True = don't raise a CancelledError into a sync activity's thread on cancel; check activity.is_cancelled() instead
#       dynamic=False,                 # True = catch-all activity invoked for any name not otherwise registered on this worker
#   )
@activity.defn
async def reference_activity(should_heartbeat: bool) -> str:
    """Companion to ReferenceWorkflow in workflows.py — see that class's
    docstring for the full execute_activity()/RetryPolicy option list."""
    if should_heartbeat:
        activity.heartbeat("reference_activity: still working")
    return "reference_activity completed"
