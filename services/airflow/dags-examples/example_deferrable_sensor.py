"""Starter example — a deferrable operator: waits for an external signal by
suspending into the `airflow-triggerer` process, holding **zero** worker
capacity for the entire wait. Contrast with `example_sensor.py`'s
`reschedule` mode, which at least frees the worker slot *between* pokes —
deferral frees it for the whole wait, full stop. A single triggerer can hold
thousands of these concurrently on one async event loop; this is the actual
mechanism real deferrable operators/sensors (S3KeySensor, TimeSensorAsync,
etc.) are built on, hand-rolled here so the mechanism itself is visible.

Two pieces, the same split every deferrable operator uses:

  MarkerFileTrigger        — runs in airflow-triggerer, async, polls via
                              asyncio.sleep (not a worker-slot-holding loop)
  WaitForMarkerFileOperator — runs in the worker just long enough to call
                              self.defer(...) and hand off to the trigger,
                              then again briefly when the trigger fires

Trigger this DAG, then watch the Grid view: the task's state shows
"deferred" — a distinct state from "running", exactly because it isn't
occupying a worker. Create the marker file to let it complete:

    docker exec airflow-scheduler touch /opt/airflow/dags/.deferrable_sensor_trigger

Or from the host, if the dags folder is bind-mounted there too:

    touch service_data/data/airflow/dags/.deferrable_sensor_trigger
"""

import asyncio
from datetime import datetime
from pathlib import Path
from typing import Any

from airflow.sdk import BaseOperator, dag
from airflow.triggers.base import BaseTrigger, TriggerEvent

MARKER_PATH = "/opt/airflow/dags/.deferrable_sensor_trigger"


class MarkerFileTrigger(BaseTrigger):
    """Runs inside airflow-triggerer, not a worker. `serialize()` is what
    makes that possible — the trigger's constructor args get pickled into
    the metadata DB and reconstructed by the triggerer process, which is
    why they must be plain, easily-serializable values (a path and a
    number), not live objects."""

    def __init__(self, marker_path: str, poll_interval: float = 5.0) -> None:
        super().__init__()
        self.marker_path = marker_path
        self.poll_interval = poll_interval

    def serialize(self) -> tuple[str, dict[str, Any]]:
        return (
            "example_deferrable_sensor.MarkerFileTrigger",
            {"marker_path": self.marker_path, "poll_interval": self.poll_interval},
        )

    async def run(self):
        # A real trigger would `await` a genuinely async I/O call here (an
        # async HTTP client, aiofiles, etc.) — asyncio.sleep is the stand-in
        # so this needs no extra dependency, same spirit as example_sensor's
        # marker-file stub.
        while not Path(self.marker_path).exists():
            await asyncio.sleep(self.poll_interval)
        yield TriggerEvent({"found": self.marker_path})


class WaitForMarkerFileOperator(BaseOperator):
    """`execute()` runs on a worker just long enough to call `self.defer()`
    and immediately hand off — it does NOT block waiting for the trigger.
    `execute_complete()` runs on a worker again, briefly, once the trigger
    yields its event; the worker is free for other tasks the entire time in
    between."""

    def __init__(self, marker_path: str, poll_interval: float = 5.0, **kwargs) -> None:
        super().__init__(**kwargs)
        self.marker_path = marker_path
        self.poll_interval = poll_interval

    def execute(self, context) -> None:
        self.defer(
            trigger=MarkerFileTrigger(self.marker_path, self.poll_interval),
            method_name="execute_complete",
        )

    def execute_complete(self, context, event: dict | None = None) -> None:
        print(f"Deferred wait complete — marker found at {event['found']}")
        Path(self.marker_path).unlink(missing_ok=True)


@dag(
    dag_id="example_deferrable_sensor",
    description="Starter example: a deferrable operator waits via the triggerer, holding zero worker slot",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_deferrable_sensor():
    WaitForMarkerFileOperator(task_id="wait_for_marker", marker_path=MARKER_PATH, poll_interval=5.0)


example_deferrable_sensor()
