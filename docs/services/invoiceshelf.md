# InvoiceShelf

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Open-source invoicing and billing — the actively maintained community successor to Crater (same Laravel + MariaDB stack, same data format; the original `foralabs/crater` image was made private).
**Port:** `8101` (host) → `8080` (container) | **Data:** `service_data/invoiceshelf/` | **Requires:** MariaDB

## Setup

```bash
cp invoiceshelf/.env.example invoiceshelf/.env
# generate: echo "base64:$(openssl rand -base64 32)" → APP_KEY
# set MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD
sh homeserver.sh dev up invoiceshelf
```

## First login

Browse to `http://<ip>:8101` — the setup wizard creates the admin account.

## Notes

- Image: `invoiceshelf/invoiceshelf`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
