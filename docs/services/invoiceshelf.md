# InvoiceShelf

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)

---

**Purpose:** Open-source invoicing and billing — the actively maintained community successor to Crater (same Laravel + MariaDB stack, same data format; the original `foralabs/crater` image was made private).
**Port:** `8101` (host) → `8080` (container) | **Data:** `service_data/data/invoiceshelf/` | **Requires:** MariaDB

## Setup

`compose.yml` bind-mounts the *entire* `/var/www/html/storage` directory (`${DATA_ROOT}/uploads:/var/www/html/storage`), which hides the subdirectories Laravel needs (`framework/cache`, `framework/sessions`, `app/templates/pdf`, etc.) that the image normally ships pre-populated — the container's entrypoint doesn't recreate them, so skipping this pre-create step fails first boot with `Please provide a valid cache path` / `The "/var/www/html/storage/app/templates/pdf" directory does not exist` and a restart loop.

```bash
cp invoiceshelf/.env.example invoiceshelf/.env
# generate: echo "base64:$(openssl rand -base64 32)" → APP_KEY
# set MYSQL_PASSWORD, MYSQL_ROOT_PASSWORD

# Required before first `up` — see note above
mkdir -p service_data/data/invoiceshelf/uploads/framework/cache/data
mkdir -p service_data/data/invoiceshelf/uploads/framework/sessions
mkdir -p service_data/data/invoiceshelf/uploads/framework/views
mkdir -p service_data/data/invoiceshelf/uploads/framework/testing
mkdir -p service_data/data/invoiceshelf/uploads/app/public
mkdir -p service_data/data/invoiceshelf/uploads/app/templates/pdf
mkdir -p service_data/data/invoiceshelf/uploads/app/estimates
mkdir -p service_data/data/invoiceshelf/uploads/app/invoices
mkdir -p service_data/data/invoiceshelf/uploads/app/company_logo
mkdir -p service_data/data/invoiceshelf/uploads/app/backup

uv run homeserver.py dev up invoiceshelf
```

## First login

Browse to `http://<ip>:8101` — the setup wizard creates the admin account.

## Notes

- Image: `invoiceshelf/invoiceshelf`

---

[← Services Reference](../11-services-reference.md) | [Home](../../setup.md)
