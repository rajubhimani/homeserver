# Ghostfolio

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Tracks your investments (stocks, ETFs, mutual funds, crypto, cash) across every broker in one place: live prices, performance over time, allocation by asset class/region/sector, dividends and fees. It's the investment-side companion to [Firefly III](firefly.md), which tracks day-to-day spending. See [Connecting to Firefly III](#connecting-to-firefly-iii) below.
**Port:** `8162` (host) → `3333` (container) | **Data:** `ghostfolio-postgres` named volume (all accounts, activities and cached market data). Nothing under `service_data/data/`. | **Requires:** Postgres, Redis (cache only, not persisted) | **Memory:** DB capped 384M in compose.yml; app and Redis have no hard limit set. Not measured yet.

Upstream: [github.com/ghostfolio/ghostfolio](https://github.com/ghostfolio/ghostfolio). Pinned to `ghostfolio/ghostfolio:3.75.0`.

## Setup

```bash
cp services/ghostfolio/.env.example services/ghostfolio/.env
# set POSTGRES_PASSWORD, REDIS_PASSWORD, ACCESS_TOKEN_SALT, JWT_SECRET_KEY
#   (openssl rand -hex 32 for each)
uv run homeserver.py dev up ghostfolio
```

The first start runs the database migrations and seed before the API answers, so the container can take a minute or two to report healthy.

Open `https://ghostfolio.<domain>/` (or `http://<host>:8162` in dev) → **Get Started**. **The first account created becomes the admin.** Ghostfolio has no username/password. Instead it shows you a **security token** once at sign-up, and that token *is* your login. Put it in Vaultwarden immediately. Admin → Users can issue a new token if one is lost.

Then, as admin:

1. **Admin Control → Overview → User Signup → off**, unless you want anyone who can reach the URL to be able to create an account.
2. **Settings (your user) → Base Currency** → e.g. `INR`. Everything is converted into this for totals.
3. **Accounts → Add** one account per broker/bank/wallet (Zerodha, Groww, a savings account, a crypto wallet...).
4. **Activities → Add / Import** your buys, sells and dividends. Imports take CSV or JSON (upload limit set to 20M in nginx-plain).

## Market data (prices)

The default data source is Yahoo Finance and doesn't need an API key. Symbols use Yahoo's format:

- NSE / BSE stocks and ETFs: `RELIANCE.NS`, `NIFTYBEES.NS`, `500325.BO`
- US stocks: `MSFT`, `VTI`
- Crypto: via CoinGecko. Setting `API_KEY_COINGECKO_DEMO` in `.env` (free key) makes that much more reliable.

Anything Yahoo doesn't have (most Indian mutual funds, FDs, PPF/EPF, gold bonds, property) goes in with data source **Manual**. You then update its price yourself (Admin Control → Market Data) or just record its value as a cash-like holding.

## Connecting to Firefly III

**There's no built-in integration.** Neither app has a Firefly/Ghostfolio connector, and they model money differently. Firefly III is double-entry bookkeeping (every rupee moves between accounts). Ghostfolio is a list of trades against securities with market prices. So the practical setup is to split the work between them and pass a small amount of data across.

### Recommended split

| What | Where it lives |
| --- | --- |
| Bank accounts, cards, salary, spending, budgets | Firefly III |
| Money *leaving* the bank to invest (SIP debit, broker top-up) | Firefly III, as a **transfer** to an asset account such as "Zerodha (cash)", or as a withdrawal/expense to a category "Investments" if you don't want the broker in Firefly at all |
| What was bought with that money: units, prices, dividends, current market value | Ghostfolio |
| Cash sitting in bank accounts, for net-worth / allocation | Both. Firefly is the source of truth and Ghostfolio gets a copy (see below) |

This keeps each app doing what it's good at. Firefly answers "where did my money go this month", and Ghostfolio answers "how are my investments doing and how is my net worth allocated".

### Option 1: manual (fine for a few accounts)

In Ghostfolio, create an account for each Firefly bank account you want in your net worth (e.g. "HDFC Savings") with no activities. Now and then, open it in Ghostfolio → **Edit** → set **Cash Balance** to what Firefly shows. Ghostfolio keeps a dated history of these balances, so its net-worth chart stays correct.

### Option 2: automatic cash-balance sync over the API

Both apps have REST APIs, and both containers are on the `homeserver` Docker network, so a small script can copy Firefly's current balance into Ghostfolio. This direction (Firefly → Ghostfolio) is the useful one. The reverse (Ghostfolio's market value → Firefly) isn't worth automating because Firefly would need a fake "revaluation" transaction for every price change.

One-time setup:

1. **Firefly token:** Firefly III → **Options → Profile → OAuth → Personal Access Tokens → Create new token**. Copy it (it's long).
2. **Firefly account IDs:** open each asset account in Firefly. The ID is the number at the end of the URL (`/accounts/show/3` → `3`).
3. **Ghostfolio security token:** the one from sign-up (see Setup).
4. **Ghostfolio account IDs:** Ghostfolio → **Accounts** → create the matching accounts (same currency as in Firefly), then open one. The UUID is in the URL. You can also use the API: `GET /api/v1/account`.

The script, e.g. saved as `service_data/scripts/firefly-to-ghostfolio.sh` (not in this repo, since it holds tokens):

```sh
#!/bin/sh
# Copies Firefly III asset-account balances into Ghostfolio account cash balances.
# Runs inside a throwaway container on the homeserver network, so it talks to
# both apps by container name and never leaves the host.
set -eu

FIREFLY_TOKEN='paste-firefly-personal-access-token'
GHOSTFOLIO_SECURITY_TOKEN='paste-ghostfolio-security-token'

# "firefly_account_id:ghostfolio_account_uuid" pairs, space-separated
MAP='3:0b6c...-uuid 7:9f1e...-uuid'

apk add --no-cache curl jq >/dev/null

GF_JWT=$(curl -fsS -X POST http://ghostfolio:3333/api/v1/auth/anonymous \
  -H 'Content-Type: application/json' \
  -d "{\"accessToken\":\"$GHOSTFOLIO_SECURITY_TOKEN\"}" | jq -r .authToken)

TODAY=$(date -u +%Y-%m-%dT00:00:00.000Z)

for pair in $MAP; do
  ff_id=${pair%%:*}
  gf_id=${pair#*:}
  balance=$(curl -fsS "http://firefly:8080/api/v1/accounts/$ff_id" \
    -H "Authorization: Bearer $FIREFLY_TOKEN" -H 'Accept: application/vnd.api+json' \
    | jq -r .data.attributes.current_balance)
  curl -fsS -X POST http://ghostfolio:3333/api/v1/account-balance \
    -H "Authorization: Bearer $GF_JWT" -H 'Content-Type: application/json' \
    -d "{\"accountId\":\"$gf_id\",\"balance\":$balance,\"date\":\"$TODAY\"}" >/dev/null
  echo "firefly #$ff_id -> ghostfolio $gf_id: $balance"
done
```

Run it (needs both `firefly` and `ghostfolio` up):

```bash
docker run --rm --network homeserver \
  -v "$PWD/service_data/scripts/firefly-to-ghostfolio.sh:/sync.sh:ro" \
  alpine:3.24.2 sh /sync.sh
```

To run it daily, add that `docker run` line to the host's crontab (e.g. `30 3 * * *`, just after Firefly's own 03:00 cron job).

Things to know:

- **Currencies must match.** The script copies the number as-is. A Firefly account in `INR` must map to a Ghostfolio account in `INR`. Ghostfolio does the conversion to your base currency itself.
- **One balance per day.** Posting again for the same day updates that day's balance, so re-running is safe.
- **The Ghostfolio security token is a full login.** Treat the script like a password file. Keep it out of git and readable only by you (`chmod 600`).
- **Firefly field name.** `current_balance` is the account's balance in its own currency, which is what's wanted here. If a future Firefly version renames it, `curl` the account once and look under `data.attributes`.

### Option 3: import investment transactions into Ghostfolio

If your broker's buys/sells only exist as Firefly transactions (not in a broker export), Firefly's **Export data** CSV has amounts and dates but no symbol, quantity or unit price. Ghostfolio needs all of those, so this doesn't map directly. Use the **broker's own** contract-note / tradebook export and convert that into Ghostfolio's import format (`Activities → Import`, or `POST /api/v1/import`, see upstream's README) instead of going through Firefly.

## Backups

Everything is in Postgres (`ghostfolio-postgres` named volume). `homeserver.py down ghostfolio` snapshots it into `service_data/backup/ghostfolio/` like every other named volume. For a copy that's independent of this app version, **Activities → ⋮ menu → Export Activities** (JSON) now and then gives a file you can re-import into any Ghostfolio instance. It contains activities and accounts but not market-price history, which is re-downloaded.

## Gotchas

- **Login is a token, not a password.** See Setup. Losing the token means an admin has to reissue it. If you're the only (admin) user and you lose it, you're locked out and have to fix it in the database.
- **`ACCESS_TOKEN_SALT` must never change** after first start. Every existing security token is hashed with it, so changing it logs everyone out permanently.
- **Signup is open by default.** Turn it off in Admin Control (Setup step 1). Until you do, anyone who can reach `ghostfolio.<domain>` can create an account. It's their own empty portfolio and doesn't expose yours, but it isn't what you want.
- **Auth.** Bucket D (admin vs. user roles, see [auth posture](../13-auth-posture.md)), so it isn't behind Authentik forward-auth. Native OIDC (`ENABLE_FEATURE_AUTH_OIDC` + `OIDC_*` env vars, marked experimental upstream) works with Authentik if you want SSO later.
- **Redis is cache only.** It runs with persistence off and no volume. Losing it on restart is expected and harmless.
