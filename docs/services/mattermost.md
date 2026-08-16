# Mattermost

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

Slack-style team chat — channels, DMs, threads, plugins (Playbooks/Calls ship in the image but need a paid license; core chat is fully free in Team Edition). Part of this stack's "playground" trio alongside Rocket.Chat and Zulip — the lightest of the three: just itself + Postgres, no MongoDB replica set, no Docker secrets, no message broker.

## Setup

```bash
cp services/mattermost/.env.example services/mattermost/.env
mkdir -p service_data/data/mattermost/{config,data,logs,plugins,client-plugins,bleve-indexes}
sudo chown -R 2000:2000 service_data/data/mattermost/   # container runs as uid 2000
uv run homeserver.py dev up mattermost
```

Open `https://mattermost.<domain>/` (or `http://<host>:8141` in dev) and create the first account — it becomes System Admin automatically (first user on a fresh install always does).

## Architecture

Two containers: `mattermost-db` (Postgres, named volume per this stack's Postgres convention) and `mattermost` itself (official `mattermost-team-edition` image, uid 2000, bind-mounted `config`/`data`/`logs`/`plugins`/`client-plugins`/`bleve-indexes` under `DATA_ROOT`).

**No custom healthcheck** — the official image is genuinely distroless (no shell, no `wget`/`curl`, not even `ls`; confirmed the `mattermost` binary itself has no ping/health subcommand). It bakes its own `HEALTHCHECK` into the image instead (`mmctl system status --local`), which `compose.yml` correctly leaves alone rather than overriding with something that can't run inside this container. Verify from the host if you ever need to check manually:

```bash
curl http://localhost:8141/api/v4/system/ping
```

## Registration

`MM_TEAMSETTINGS_ENABLEOPENSERVER`/`MM_TEAMSETTINGS_ENABLEUSERCREATION` (both `true` by default) — anyone who can reach the server can self-register. Set to `false` in `.env` for admin-provisioned accounts only.

## Notes

- **Resource usage**: this is part of a "try it and see" playground (Rocket.Chat/Zulip alongside it) — bring it up when you want it, down when you don't (`uv run homeserver.py dev down mattermost`), rather than leaving it running idle. `down` auto-snapshots first, same as every other service.
- **Outgoing email routed through the shared [Mailpit](mailpit.md) catcher by default** (`MM_EMAILSETTINGS_SMTPSERVER=mailpit` in `compose.yml`) — invites/notifications genuinely send, nothing ever leaves this host. Point `MM_EMAILSETTINGS_SMTPSERVER`/etc. at a real relay instead in `.env` if you want actual delivery.
- **Playbooks/Calls plugins log "requires a professional license or higher"** on startup — expected in Team Edition, not an error; core messaging is unaffected.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
