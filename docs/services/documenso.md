# Documenso

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Self-hosted document e-signing (DocuSign alternative).
**Port:** `8128` (host) → `3000` (container) | **Data:** `service_data/data/documenso/` | **Requires:** Postgres, plus a signing certificate (see below)

## Setup — a signing certificate is required before first start

Documenso digitally signs documents with a PKCS#12 (`.p12`) certificate, and the container **will not start correctly without one** at `service_data/data/documenso/cert.p12`. A self-signed one is fine for personal/internal use (buy a real one only if documents need to be externally verifiable by third parties):

```bash
docker run --rm --entrypoint sh -v "$(pwd)/service_data/data/documenso:/out" alpine/openssl -c "
  cd /out &&
  openssl genrsa -out private.key 2048 &&
  openssl req -new -x509 -key private.key -out certificate.crt -days 3650 -subj '/CN=documenso.local' &&
  openssl pkcs12 -export -out cert.p12 -inkey private.key -in certificate.crt -passout pass: -legacy &&
  rm private.key certificate.crt
"
```

Then:

```bash
cp documenso/.env.example documenso/.env
# set POSTGRES_PASSWORD, NEXTAUTH_SECRET, NEXT_PRIVATE_ENCRYPTION_KEY,
# NEXT_PRIVATE_ENCRYPTION_SECONDARY_KEY (openssl rand -base64 32 each), and SMTP settings
uv run homeserver.py dev up documenso
```

Open `https://documenso.<domain>/` (or `http://<host>:8128` in dev) and create the first account.

## Registration

Self-registration is on by default through the UI — no env var toggle is documented; if you need to close it, check Documenso's own admin settings once running.

## Notes

- `NEXT_PRIVATE_SIGNING_PASSPHRASE` is empty by default (matching the passphrase-less cert generated above) — set both together if you generate a cert with a real passphrase.
- SMTP is required for actually sending signing-request emails, not just cosmetic — fill in `NEXT_PRIVATE_SMTP_*` for real use.
- Health endpoint: `/api/health`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
