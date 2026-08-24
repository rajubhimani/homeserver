"""Starter example — dynamic task mapping: the number of task instances is
decided at *runtime*, not when the DAG file is parsed. Every other example
here has a fixed set of tasks written by hand (`example_parallel_tasks.py`'s
3 fetch tasks are still 3 tasks even if you never call them) — this is the
real answer to "I don't know how many things I'll need to process until the
DAG actually runs" (a variable number of files landing in a bucket, rows in
a query, source systems, etc.).

    list_sources()                  (level 0 — decides the *shape* of level 1 at runtime)
      .partial(...).expand(...)     (level 1 — one mapped task instance per item)
        -> sum_totals               (level 2 — receives the whole collected list, not one item)

`process_source.partial(multiplier=10).expand(source=list_sources())` creates
one task instance per item `list_sources()` returns — change what it returns
and the Grid view shows a different number of `process_source` boxes on the
next run, with no DAG code change. `partial()` pins the arguments that stay
the same across every mapped instance (`multiplier`); `expand()` is the
argument that varies per instance (`source`). `sum_totals` receives the full
list of every mapped instance's return value automatically — Airflow calls
this an XCom "aggregated" value, no manual xcom_pull loop needed.

Try changing what `list_sources()` returns (e.g. `range(2)` or `range(20)`)
and re-trigger — the number of `process_source` boxes in the Graph view
changes to match, entirely decided by data, not by editing this file.
"""

from datetime import datetime

from airflow.sdk import dag, task


@dag(
    dag_id="example_dynamic_task_mapping",
    description="Starter example: expand()/partial() create task instances at runtime",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_dynamic_task_mapping():
    @task
    def list_sources() -> list[str]:
        # Real version: list files in a bucket, rows in a control table, etc.
        # The point is this list's *length* isn't known until the DAG runs.
        return ["source_a", "source_b", "source_c", "source_d"]

    @task
    def process_source(source: str, multiplier: int) -> int:
        # Real version: fetch/transform that one source. Each of these runs
        # as its own task instance — its own log, its own retry count, its
        # own row in the Grid view — even though there's one function here.
        value = len(source) * multiplier
        print(f"Processed {source} -> {value}")
        return value

    @task
    def sum_totals(values: list[int]) -> None:
        # `values` is every process_source instance's return value, collected
        # automatically — this is what "aggregated XCom" means in the Airflow
        # UI's mapped-task view.
        print(f"Sum across {len(values)} mapped instances: {sum(values)}")

    totals = process_source.partial(multiplier=10).expand(source=list_sources())
    sum_totals(totals)


example_dynamic_task_mapping()
