# RunContainerWorkflow

[← Temporal](../temporal.md) | [Home](../../../../setup.md)

---

Resource-bounded execution. The worker has `${DOCKER_SOCKET}` mounted; its Activity calls the Docker SDK with explicit `mem_limit`/`cpu_count`, so a step's actual container never has an unbounded footprint on the host — the same pattern as Airflow's [`example_docker_operator`](../../airflow/examples/example_docker_operator.md).

📍 `services/temporal/worker/workflows.py:28` (workflow) / `services/temporal/worker/activities.py:24` (`run_container_activity`)

```mermaid
sequenceDiagram
    participant C as caller
    participant W as RunContainerWorkflow
    participant A as run_container_activity
    participant D as Docker (host socket)

    C->>W: start(RunContainerInput)
    W->>A: execute_activity(mem_limit, cpu_count)
    A->>D: containers.run(...)
    D-->>A: container output
    A-->>W: output string
    W-->>C: result
```

## Try it

```bash
docker exec -it temporal-admin-tools temporal workflow start --address temporal:7233 \
  --task-queue homeserver \
  --type RunContainerWorkflow \
  --input '{"image": "alpine:3.21", "command": ["echo", "hello"], "mem_limit": "128m", "cpu_count": 1}'
```

---

[← Temporal](../temporal.md) | [Home](../../../../setup.md)
