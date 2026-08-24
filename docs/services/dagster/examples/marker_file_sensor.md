# marker_file_sensor

[← Dagster](../dagster.md) | [Home](../../../../setup.md)

---

Dagster's parallel to Airflow's Sensor — reacts to an external signal instead of a fixed schedule, same self-contained marker-file pattern as [`example_sensor`](../../airflow/examples/example_sensor.md).

**Real-world problem:** a partner system drops a file into a shared folder whenever it has new data ready — sometimes twice a day, sometimes not for a week. A fixed hourly schedule either wastes runs checking for nothing, or leaves data sitting unprocessed for up to an hour after it actually arrives.

📍 `services/dagster/user-code/definitions.py:322`

```mermaid
flowchart LR
    marker_file_sensor -->|marker file exists?<br/>every 15s min| Check{marker found?}
    Check -->|no| SkipReason
    Check -->|yes, unlink it| RunRequest -.-> report_job
```

Turn it on from the **Sensors** tab (sensors default to off), then from *inside the `dagster-user-code` container specifically* — that's where sensor code actually executes, not `dagster-daemon` (bit this exact mismatch during development).

## Try it

```bash
docker exec dagster-user-code touch /tmp/io_manager_storage/.dagster_sensor_trigger
```

---

[← Dagster](../dagster.md) | [Home](../../../../setup.md)
