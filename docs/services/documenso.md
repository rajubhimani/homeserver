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
cp services/documenso/.env.example services/documenso/.env
# set POSTGRES_PASSWORD, NEXTAUTH_SECRET, NEXT_PRIVATE_ENCRYPTION_KEY,
# NEXT_PRIVATE_ENCRYPTION_SECONDARY_KEY (openssl rand -base64 32 each), and SMTP settings
uv run homeserver.py dev up documenso
```

Open `https://documenso.<domain>/` (or `http://<host>:8128` in dev) and create the first account.

## Registration

Self-registration is on by default (`NEXT_PUBLIC_DISABLE_SIGNUP=false` in `.env.example`). Set it to `true` to close the instance to new signups.

## Using it day to day

No mobile app — web-only (`https://documenso.${DOMAIN}`), by design of the product (a document gets signed by whoever receives the emailed link, who may never have an account at all).

- **Upload a document → add signature fields** (drag onto the PDF preview: signature, initials, date, text, checkbox) → **assign each field to a signer** by email → **send**. Each recipient gets an emailed link to sign their assigned fields, no account required on their end.
- **Templates** save a field layout for reuse on future documents of the same shape (e.g. a standard contract), instead of re-placing fields every time.
- **Audit trail**: every signed document gets a certificate page appended recording signer IP, timestamp, and consent — this is what makes it usable as more than a decorative signature.

## Notes

- `NEXT_PRIVATE_SIGNING_PASSPHRASE` is empty by default (matching the passphrase-less cert generated above) — set both together if you generate a cert with a real passphrase.
- **Outgoing signing-request email is already wired to this stack's Mailpit** (`NEXT_PRIVATE_SMTP_HOST=mailpit` in `.env.example`) for testing — see [mailpit.md](mailpit.md) to view captured emails, including the actual signing links, since nothing is delivered externally until this is pointed at real SMTP credentials.
- Health endpoint: `/api/health`.

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
