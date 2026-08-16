# hello_homeserver

[← Dagster](dagster.md) | [Home](../../../setup.md)

---

The simplest possible asset — one function, no dependencies, no config. Start here if you've never used Dagster before.

📍 `services/dagster/user-code/definitions.py:114`

```mermaid
flowchart LR
    hello_homeserver
```

## Try it

Select it in the UI's **Assets** tab → **Materialize selected**, or via GraphQL:

```bash
docker exec dagster-webserver dagster-graphql -r http://localhost:3000 -p launchPipelineExecution -v '{
  "executionParams": {
    "selector": {"repositoryLocationName": "user_code", "repositoryName": "__repository__", "pipelineName": "__ASSET_JOB", "assetSelection": [{"path": ["hello_homeserver"]}]},
    "mode": "default"
  }
}'
```

---

[← Dagster](dagster.md) | [Home](../../../setup.md)
