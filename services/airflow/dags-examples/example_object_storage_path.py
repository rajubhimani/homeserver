"""Starter example — `ObjectStoragePath` (AIP-58, since Airflow 2.8): a
`pathlib.Path`-like abstraction over object stores. Not a task/scheduling
primitive like every other example here — it's Airflow's built-in answer
to "write storage-agnostic DAG code" so a DAG doesn't hardcode `boto3`/
`google-cloud-storage`/raw `open()` calls tied to one specific backend.

This DAG uses the `file://` (local filesystem) backend — zero cloud
credentials needed — but the exact same code, unchanged, would target
`s3://`/`gs://`/`abfs://` by swapping the URI scheme and pointing at a
Connection (`ObjectStoragePath("s3://bucket/key", conn_id="aws_default")`).
That portability, not the local demo itself, is the actual point.

    docker exec airflow-scheduler airflow dags unpause example_object_storage_path
    docker exec airflow-scheduler airflow dags trigger example_object_storage_path
"""

from datetime import datetime

from airflow.sdk import ObjectStoragePath, dag, task

BASE = ObjectStoragePath("file:///opt/airflow/dags/.object_storage_demo/")


@dag(
    dag_id="example_object_storage_path",
    description="Starter example: ObjectStoragePath — storage-agnostic DAG code, local backend here",
    doc_md=__doc__,
    start_date=datetime(2026, 1, 1),
    schedule=None,
    catchup=False,
    tags=["example"],
)
def example_object_storage_path():
    @task
    def write_object() -> str:
        BASE.mkdir(exist_ok=True, parents=True)
        path = BASE / "report.txt"
        path.write_text("Same ObjectStoragePath code works against s3://, gs://, abfs://.")
        return str(path)

    @task
    def read_object(path_str: str) -> None:
        path = ObjectStoragePath(path_str)
        print(f"Read back from {path}: {path.read_text()!r}")
        print(f"Exists before cleanup: {path.exists()}")
        path.unlink()
        print(f"Exists after cleanup: {path.exists()}")

    read_object(write_object())


example_object_storage_path()
