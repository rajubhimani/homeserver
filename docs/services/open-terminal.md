# Open Terminal

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** A code-execution sandbox for [Open WebUI](open-webui.md). A model with tool calling can run shell commands and Python in a real container, install any library, read and write files, and hand results back to the chat. It replaces Open WebUI's built-in Pyodide/Jupyter code interpreter, which Open WebUI's docs now call legacy (Pyodide has a fixed package list and no pip).
**Port:** `8164` (host, dev) → `8000` (container) | **Part of:** the `open-webui` service (same compose file, `up open-webui` starts both; there is no separate service or tier entry) | **Memory:** idle is small; depends on what the model runs

## Setup

```bash
uv run homeserver.py dev up open-webui     # starts open-terminal with it
```

Everything lives in `services/open-webui/.env` (the `OPEN_TERMINAL_*` block): the API key, image tag and package lists. Open WebUI's `compose.yml` turns `OPEN_TERMINAL_URL` + `OPEN_TERMINAL_API_KEY` into `TERMINAL_SERVER_CONNECTIONS`, so the connection exists on first start with no clicking. The `open-terminal` container gets only the `OPEN_TERMINAL_*` values (an explicit `environment:` list, not `env_file`), so the model's shell can never read `WEBUI_SECRET_KEY`. Open WebUI's backend calls the terminal over the internal `homeserver` network (it reverse-proxies terminal requests), so the port is never exposed publicly and there is no subdomain.

**`TERMINAL_SERVER_CONNECTIONS` is a persistent setting, and a saved value beats the environment variable.** Open WebUI writes every setting to its database (`config` table, key `terminal_server.connections`) the first time it sees it, with an empty `[]` if the variable was unset then. This stack hit exactly that (2026-10-18): the container had the variable, but the terminal never appeared in chats because the database still held `[]`. Two ways to fix or change it:

- **Admin Settings → Integrations → Open Terminal** (the *admin* page, not Settings → Integrations in your own user menu: that one is per-user and always shows "No terminal connections configured"). Add `http://open-terminal:8000`, bearer auth, the key from `.env`.
- Or write the row directly while the container runs (it is read on each request, no restart needed):

```bash
docker exec -i -e KEY=<OPEN_TERMINAL_API_KEY> open-webui python3 - <<'PY'
import sqlite3, json, os, time
db = sqlite3.connect('/app/backend/data/webui.db')
conn = [{"id": "open-terminal", "name": "Open Terminal", "url": "http://open-terminal:8000",
         "auth_type": "bearer", "key": os.environ['KEY'], "enabled": True}]
db.execute("update config set value=?, updated_at=? where key='terminal_server.connections'",
           (json.dumps(conn), int(time.time())))
db.commit()
PY
```

A changed `OPEN_TERMINAL_API_KEY` needs the same update. Admins see the connection automatically; other users need access grants on it.

In a chat, the terminal selector appears next to the message box only for models whose Terminal capability is on (the default) while tool servers are enabled (`ENABLE_TOOL_SERVERS`, default true). Reload the page after changing the connection.

Then use native tool calling on the model (Advanced Params → Function Calling → Native; the default since Open WebUI 0.10) and pick a model with good tool use, such as `gpt-oss:20b`.

## Libraries

The default image already ships numpy, pandas, scipy, scikit-learn, matplotlib, seaborn, plotly, requests, beautifulsoup4, lxml, sqlalchemy, openpyxl, python-docx, python-pptx, pypdf, jupyter, plus LibreOffice, pandoc, ffmpeg, poppler, ImageMagick, Node.js and a full build toolchain.

On top of that, `OPEN_TERMINAL_PIP_PACKAGES` installs at every start:

| Area | Packages |
|---|---|
| ML / DL | torch, torchvision, torchaudio (CPU builds: the host has no GPU), transformers, sentence-transformers, onnxruntime, xgboost, lightgbm, optuna, shap, imbalanced-learn, statsmodels |
| Data | polars, duckdb (library + the `duckdb` CLI from the first-party `duckdb-cli` PyPI package), pyarrow, xlsxwriter, sympy, networkx |
| APIs / databases | fastapi, uvicorn, sqlalchemy, alembic |
| Pipelines | pydantic, tenacity, python-dotenv, pytest, ruff |
| Scraping | httpx, scrapy, trafilatura, html5lib, feedparser |
| Documents | pdfplumber, pymupdf, reportlab, markitdown, docx2txt, pytesseract (+ apt `tesseract-ocr`), pdf2image, pillow, opencv-python-headless |

To add more, append to `OPEN_TERMINAL_PIP_PACKAGES` in `services/open-webui/.env` (space-separated; options such as `--extra-index-url` work too), `OPEN_TERMINAL_PACKAGES` (apt) or `OPEN_TERMINAL_NPM_PACKAGES`, then `uv run homeserver.py dev restart open-webui`. The model can also `pip install` ad hoc inside a chat; those installs persist in the home volume.

**First start is slow** (several GB of wheels, PyTorch is the bulk), and the healthcheck's `start_period` is 900 s to cover it. Later starts only re-check what is installed. Do not use the `slim`/`alpine` image variants: they ignore the package variables. TensorFlow and Playwright (browser download) are not preinstalled; add them if needed.

## Data paths

`TERMINAL_HOME_ROOT` (`service_data/cache/open-webui/terminal-home`) is the container's `/home/user`: workspace files plus pip/npm installs. It is in the `cache/` bucket, not `data/`, so snapshots skip it. Treat it as a scratch sandbox: deleting it costs only a package re-install and any files the model left there. It sits next to Open WebUI's other cache and is not part of `DATA_ROOT`.

## Security

The model gets a real shell with passwordless sudo inside the container, so treat the container as untrusted.

- **Do not mount the Docker socket** (the image ships the Docker CLI): that is root on the host.
- No public route and no subdomain, on purpose. Only Open WebUI reaches it, with the bearer key.
- The container has full outbound internet. To restrict it, set `OPEN_TERMINAL_ALLOWED_DOMAINS` (comma-separated; empty blocks everything), which needs `NET_ADMIN`; not enabled here.
- Leave `OPEN_TERMINAL_MULTI_USER=false`: the upstream docs say multi-user mode separates workspaces but is not a security boundary.

## Health endpoint

`GET /health` on port 8000 (the compose healthcheck runs `curl -sf` on it). No landing-page card or `/health/` route: it has no UI of its own.

## Notes

- Version: no LTS track, so the newest release (`0.14.1`, 2026-10-16). Update by changing `OPEN_TERMINAL_IMAGE_TAG`.
- Upstream: <https://github.com/open-webui/open-terminal>.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
