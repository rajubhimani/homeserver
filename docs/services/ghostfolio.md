# Ghostfolio

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Tracks your investments (stocks, ETFs, mutual funds, crypto, cash) across every broker in one place: live prices, performance over time, allocation by asset class/region/sector, dividends and fees. It's the investment-side companion to [Firefly III](firefly.md), which tracks day-to-day spending. [`firefly-sync.sh`](#connecting-to-firefly-iii) keeps Firefly's net worth in line with Ghostfolio's market values.
**Port:** `8162` (host) → `3333` (container) | **Data:** `ghostfolio-postgres` named volume (all accounts, activities and cached market data). Nothing under `service_data/data/`. | **Requires:** Postgres, Redis (cache only, not persisted) | **Memory:** database on `shared-postgres` (counted there); app and Redis have no hard limit set. Not measured yet.

**Database:** on the shared Postgres server ([shared-postgres](shared-postgres.md)), not its own container — since 2026-10-01. `homeserver.py` starts `shared-postgres` before this service and creates its database and login from `POSTGRES_DB`, `POSTGRES_USER`, `POSTGRES_PASSWORD` in `services/ghostfolio/.env` (the `shared_db` entry in `services.json`); snapshots include a dump of just this service's database.


Upstream: [github.com/ghostfolio/ghostfolio](https://github.com/ghostfolio/ghostfolio). Pinned to `ghostfolio/ghostfolio:3.77.0`.

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
2. **Admin Control → Market Data → `+` → switch to Add Currency → `INR`**, then **Settings (your user) → Base Currency → `INR`**. Everything is converted into this for totals. On a fresh install the Base Currency list only offers `USD`, because it lists just the currencies Ghostfolio already knows about (stored in the admin `CURRENCIES` property, empty at first). Adding INR first also makes Ghostfolio fetch the `USDINR` exchange rate.
3. **Accounts → Add** one account per broker/bank/wallet (Zerodha, Groww, a savings account, a crypto wallet...).
4. **Activities → Add / Import** your buys, sells and dividends. Imports take CSV or JSON (upload limit set to 20M in nginx-plain).

## Market data (prices)

The default data source is Yahoo Finance and doesn't need an API key. Symbols use Yahoo's format:

- NSE / BSE stocks and ETFs: `RELIANCE.NS`, `NIFTYBEES.NS`, `500325.BO`
- US stocks: `MSFT`, `VTI`
- Crypto: via CoinGecko. Setting `API_KEY_COINGECKO_DEMO` in `.env` (free key) makes that much more reliable.

Anything Yahoo doesn't have (most Indian mutual funds, FDs, PPF/EPF, gold bonds, property) goes in with data source **Manual**. You then update its price yourself (Admin Control → Market Data) or just record its value as a cash-like holding.

## Connecting to Firefly III

Goal: Firefly III stays your one place for **net worth**, including investments at today's market price, while Ghostfolio does the investment tracking that Firefly can't.

### What the research turned up (Sep 2026)

- **There's no ready-made Ghostfolio ↔ Firefly connector.** Nothing on GitHub's [ghostfolio topic](https://github.com/topics/ghostfolio) does this. The projects there are broker importers ([Export-To-Ghostfolio](https://github.com/dickwolff/Export-To-Ghostfolio), [GhostfolioSidekick](https://github.com/VibeNL/GhostfolioSidekick), an IBKR sync). The only project that combines the two, [Balancr](https://github.com/nrosier/Balancr/issues/656), reads both into its *own* dashboard rather than syncing one into the other.
- **Firefly won't track investments itself.** Its maintainer has said it "is not meant for tracking investments" and pointed people to Portfolio Performance ([discussion #10190](https://github.com/orgs/firefly-iii/discussions/10190)). A request for Yahoo-price holdings was closed as *not planned* ([#10949](https://github.com/firefly-iii/firefly-iii/issues/10949)).
- **What Firefly users actually do:** keep the investment account as a normal **asset account**, record money going in and out as transfers, and every so often book the **change in market value** as a gain/loss transaction so the balance matches the broker. The maintainer confirms this is the intended workaround: "It is of course entirely possible to create win/loss transactions. Daily or weekly, whatever you prefer" ([#10190](https://github.com/orgs/firefly-iii/discussions/10190)). Others do it monthly ([#11922](https://github.com/orgs/firefly-iii/discussions/11922)). Book only the *difference* from the last value, never the total, or the balance keeps growing ([#4471](https://github.com/orgs/firefly-iii/discussions/4471)).
- **Closest existing automation:** [firefly-bridge's `portfolio-sync`](https://github.com/rajkumaar23/firefly-bridge) does exactly that on a schedule. It keeps holdings as text in the Firefly account's notes (`AAPL=10,VTSAX=50`), fetches prices, and posts Profit/Loss transactions. It prices the holdings itself, though, so you'd be keeping the same holdings in two places. With Ghostfolio already here, it makes more sense to take the value **from Ghostfolio**.

So this stack does the community's gain/loss method, automated, with Ghostfolio as the price source: [`services/ghostfolio/firefly-sync.sh`](../../services/ghostfolio/firefly-sync.sh).

### How the two apps split the work

| What | Source of truth | Goes to the other app as |
| --- | --- | --- |
| Bank accounts, cards, salary, spending, budgets | Firefly | Bank balance → Ghostfolio account cash balance (`CASH_MAP`), so Ghostfolio's allocation includes your cash |
| Money you send to a broker (SIP debit, top-up) | Firefly, as a **transfer** from the bank account to the broker's asset account | (nothing, it's already in Firefly) |
| Holdings, units, prices, dividends | Ghostfolio | Market value → a gain/loss transaction for the difference in Firefly (`INVEST_MAP`), so Firefly's net worth is current |

Each account is synced in **one direction only**. A bank account goes in `CASH_MAP`, a broker/investment account goes in `INVEST_MAP`, and never the same account in both, or the two directions fight each other.

### What it looks like in Firefly

Say you move ₹10,000 from HDFC to Zerodha in Firefly (a transfer), and Ghostfolio says your Zerodha holdings are now worth ₹1,23,456. Firefly's "Zerodha" account shows ₹1,00,000, so the next sync books:

- a **deposit** of ₹23,456 from the revenue account *Investment gains* into *Zerodha*,
- category *Unrealized gains/losses*, tag `ghostfolio-sync`, description "Market value update (Ghostfolio)".

If the market falls, it's a **withdrawal** from *Zerodha* to the expense account *Investment losses* instead. The Zerodha balance now equals Ghostfolio's value, and Firefly's net worth (dashboard and reports) includes it. The names are configurable. Firefly creates the revenue/expense accounts automatically the first time they're used.

Two things keep your spending reports clean:

- **Put the gain/loss out of the way.** In Firefly, filter or exclude the *Unrealized gains/losses* category (or the `ghostfolio-sync` tag) in reports. Otherwise a good market month looks like income and a bad one like spending.
- **Record contributions as transfers.** The script books *whatever* the difference is. If you buy ₹10,000 of shares but never recorded the transfer in Firefly, the next run books that ₹10,000 as a "gain". Net worth is still correct, but the gain is overstated.

### Setup

1. **Firefly token:** Firefly III → **Options → Profile → OAuth → Personal Access Tokens → Create new token**. Copy it (it's long).
2. **Firefly accounts:** one **asset account** per broker/investment account (e.g. "Zerodha", "Groww MF"), same currency as in Ghostfolio, with **Include in net worth** on. For the first sync, set its opening balance to what you've invested so far, or leave it at 0 and let the first sync book the whole value once. The account ID is the number at the end of its URL (`/accounts/show/7` → `7`).
3. **Ghostfolio accounts:** in **Accounts**, one per broker (with its activities) and one per bank account you want in `CASH_MAP` (no activities). Open one and the UUID is in the URL.
4. Configure and do a dry run:

   ```bash
   cp services/ghostfolio/sync.env.example services/ghostfolio/sync.env   # gitignored
   chmod 600 services/ghostfolio/sync.env
   # fill in FIREFLY_TOKEN, GHOSTFOLIO_SECURITY_TOKEN, and e.g.
   #   CASH_MAP="3:<hdfc-uuid>"
   #   INVEST_MAP="7:<zerodha-uuid> 8:<groww-uuid>"
   # and set DRY_RUN=1 for the first run
   sh services/ghostfolio/firefly-sync.sh
   ```

   Output looks like:

   ```
   cash   firefly #3 -> ghostfolio HDFC: 50000.00
   invest ghostfolio Zerodha 123456.78 vs firefly #7 100000.00: booking 23456.78
   invest ghostfolio Groww 199950.0 vs firefly #8 200000.00: diff -50.00 below 100, nothing to do
   ```

   Compare each Ghostfolio number with the **Value** column on Ghostfolio's Accounts page. Once it matches, set `DRY_RUN=0`.

5. **Schedule it** in the host crontab (`crontab -e`), from the repo root:

   ```
   30 18 * * 1-5  cd /path/to/homeserver && sh services/ghostfolio/firefly-sync.sh >> "$HOME/firefly-sync.log" 2>&1
   ```

   That's weekdays after Indian market close. Daily is fine because `MIN_DELTA` (default 100) skips small moves, so Firefly doesn't get a transaction for every wiggle. For fewer transactions, run it weekly or monthly, which is what most people doing this by hand settle on.

How it runs: the script starts a throwaway `alpine` container on the `homeserver` network and talks to `firefly:8080` and `ghostfolio:3333` directly, so nothing goes through nginx/Cloudflare and nothing is installed on the host. Both services must be up. If either is down, the run fails without writing anything.

### Things to know

- **Currencies must match.** Ghostfolio's per-account `value` is in the account's own currency, and the script copies it as-is. It checks that the Firefly and Ghostfolio accounts use the same currency code and skips the pair if they don't.
- **Cash at the broker.** Ghostfolio's account value includes that account's cash balance. If you also record broker cash in a separate Firefly account, you'd count it twice. Keep broker cash inside the broker's single Firefly asset account.
- **Re-running is safe.** Cash balances in Ghostfolio are one-per-day (a second run overwrites that day). A gain/loss is only booked while the difference is at least `MIN_DELTA`, and once booked the difference is ~0, so an immediate re-run does nothing.
- **Mistakes are easy to undo.** Every transaction the script creates has the tag `ghostfolio-sync`. Open the tag in Firefly to see them all, and delete any bad ones. The next run re-books the correct difference.
- **Manual-price holdings** (most mutual funds, FDs, PPF, see [Market data](#market-data-prices)) are only as current as the last price you entered in Ghostfolio, so Firefly is too.
- **Tokens.** `sync.env` holds a full Ghostfolio login and a Firefly token that can write to your books. It's gitignored, keep it `chmod 600`. It's deliberately separate from `services/ghostfolio/.env` so the Firefly token never ends up inside the Ghostfolio container.
- **Firefly field names.** The script reads `current_balance` and `currency_code` from Firefly's account API. If a Firefly upgrade renames them, the dry run will show `null`. `curl` one account and check `data.attributes`.

### Doing it by hand instead

The same method without the script: once a month, open the Zerodha account in Firefly, compare its balance with Ghostfolio's value, and add one deposit (from *Investment gains*) or withdrawal (to *Investment losses*) for the difference. Firefly's **Reconcile** button on an asset account does the same thing and books the difference as a reconciliation transaction.

### Importing investment transactions into Ghostfolio

Firefly's export has amounts and dates but no symbol, quantity or unit price, so it can't feed Ghostfolio's activities. Use the broker's own tradebook export instead, with Ghostfolio's **Activities → Import**, or a converter like [Export-To-Ghostfolio](https://github.com/dickwolff/Export-To-Ghostfolio).

## Backups

Everything is in Postgres (`ghostfolio-postgres` named volume). `homeserver.py down ghostfolio` snapshots it into `service_data/backup/ghostfolio/` like every other named volume. For a copy that's independent of this app version, **Activities → ⋮ menu → Export Activities** (JSON) now and then gives a file you can re-import into any Ghostfolio instance. It contains activities and accounts but not market-price history, which is re-downloaded.

## Gotchas

- **Login is a token, not a password.** See Setup. Losing the token means an admin has to reissue it. If you're the only (admin) user and you lose it, you're locked out and have to fix it in the database.
- **`ACCESS_TOKEN_SALT` must never change** after first start. Every existing security token is hashed with it, so changing it logs everyone out permanently.
- **Signup is open by default.** Turn it off in Admin Control (Setup step 1). Until you do, anyone who can reach `ghostfolio.<domain>` can create an account. It's their own empty portfolio and doesn't expose yours, but it isn't what you want.
- **Auth.** Bucket D (admin vs. user roles, see [auth posture](../13-auth-posture.md)), so it isn't behind Authentik forward-auth. Native OIDC (`ENABLE_FEATURE_AUTH_OIDC` + `OIDC_*` env vars, marked experimental upstream) works with Authentik if you want SSO later.
- **Redis is cache only.** It runs with persistence off and no volume. Losing it on restart is expected and harmless.
