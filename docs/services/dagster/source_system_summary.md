# source_system_summary

[← Dagster](dagster.md) | [Home](../../../setup.md)

---

Uses a **Resource** (`SourceSystemResource`) — how an asset gets a configurable connection to something external (an API base URL, credentials) instead of hardcoding a client inline. The asset's `source_system: SourceSystemResource` parameter is a giveaway that it's a dependency injection, not a lineage edge — Dagster checks the `Definitions(resources=...)` dict for a matching key first, *then* falls back to treating the parameter as another asset.

📍 `services/dagster/user-code/definitions.py:208` (`SourceSystemResource`) / `:221` (`source_system_summary`)

```mermaid
flowchart LR
    Res[("SourceSystemResource<br/>base_url (config)")] -.->|injected via Definitions resources=| source_system_summary
```

Swapping environments means changing the `SourceSystemResource(...)` value passed into `Definitions`, not the asset's code.

## Try it

```bash
docker exec dagster-webserver dagster-graphql -r http://localhost:3000 -p launchPipelineExecution -v '{
  "executionParams": {
    "selector": {"repositoryLocationName": "user_code", "repositoryName": "__repository__", "pipelineName": "__ASSET_JOB", "assetSelection": [{"path": ["source_system_summary"]}]},
    "mode": "default"
  }
}'
```

---

[← Dagster](dagster.md) | [Home](../../../setup.md)
