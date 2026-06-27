# 12 — VPN Services

[← Services Reference](11-services-reference.md) | [Home](../setup.md)

---

Three independent VPN services. Start any combination depending on what you need.

| Service | Use case | Clients | Port |
| --- | --- | --- | --- |
| **wg-easy** | WireGuard — modern, fast, split or full tunnel | All platforms | `51820/udp`, UI: `51821` |
| **headscale** | Mesh network — peer-to-peer, no bottleneck | Tailscale app on all platforms | `8085`, Admin: `9090` |
| **openvpn** | OpenVPN — broadest compatibility, corporate firewalls | All platforms | `1194/udp` |

---

## wg-easy — WireGuard VPN

Best for giving employees access to internal resources (split tunnel) or routing all their traffic through your server (full tunnel).

### First-time setup

**1. Generate a password hash**

```bash
docker run --rm -it ghcr.io/wg-easy/wg-easy wgpw YOUR_PASSWORD
```

Copy the hash output.

**2. Create your `.env`**

```bash
cp wg-easy/.env.example wg-easy/.env
```

Edit `wg-easy/.env`:

- `WG_HOST` — your server's public IP or domain name
- `WG_PASSWORD_HASH` — paste the hash from step 1
- `WG_ALLOWED_IPS` — controls what traffic goes through VPN:
  - Full tunnel (all traffic): `0.0.0.0/0,::/0`
  - Split tunnel (LAN only): `192.168.1.0/24` (use your actual subnet)

**3. Open firewall port**

```bash
sudo ufw allow 51820/udp
```

**4. Start**

```bash
./homeserver.sh dev up wg-easy      # dev
./homeserver.sh prod up wg-easy     # prod
```

### Web UI

- Dev: `http://your-server-ip:51821`
- Prod: proxied via nginx at e.g. `https://vpn.yourdomain.com`

From the web UI you can add employees (one config per person/device), and they download a config file or scan a QR code.

### Client apps

| Platform | App |
| --- | --- |
| Windows / Mac / Linux | [wireguard.com/install](https://www.wireguard.com/install/) |
| iOS / Android | WireGuard app from App Store / Play Store |

### Split vs full tunnel

Change `WG_ALLOWED_IPS` in `.env` then restart:

```bash
./homeserver.sh dev down wg-easy && ./homeserver.sh dev up wg-easy
```

Split tunnel example (employees only reach your LAN, their normal internet is unaffected):

```env
WG_ALLOWED_IPS=192.168.1.0/24
```

Full tunnel (all employee internet goes through your server — useful for security/filtering):

```env
WG_ALLOWED_IPS=0.0.0.0/0,::/0
```

---

## headscale — Self-hosted Tailscale Control Server

Best for mesh networking: devices connect directly to each other without routing through your server. No traffic bottleneck. Good for accessing internal tools, SSH, etc.

Employees install the standard **Tailscale** app and point it at your headscale server instead of Tailscale's cloud.

### First-time setup

**1. Edit the headscale config**

```bash
nano headscale/config/config.yaml
```

Set `server_url` to your public domain (must be HTTPS in prod):

```yaml
server_url: https://headscale.yourdomain.com
```

**2. Create your `.env`**

```bash
cp headscale/.env.example headscale/.env
```

**3. Start**

```bash
./homeserver.sh dev up headscale
```

**4. Create an API key for the admin UI**

```bash
docker exec headscale headscale apikeys create
```

Copy the key — you'll need it to log into the admin UI.

**5. Create a user (one per employee or team)**

```bash
docker exec headscale headscale users create alice
```

**6. Generate a pre-auth key for the user**

```bash
docker exec headscale headscale preauthkeys create --user alice --reusable --expiration 24h
```

Give this key to the employee for device registration.

### Admin UI

- Dev: `http://your-server-ip:9090`
- Prod: proxied via nginx at e.g. `https://headscale-admin.yourdomain.com`

Log in with the API key from step 4.

### Employee device setup

Employees install the Tailscale app, then run:

**Mac / Linux:**

```bash
tailscale up --login-server=https://headscale.yourdomain.com --authkey=<preauthkey>
```

**Windows:** use Tailscale GUI, set custom control server to your headscale URL.

**iOS / Android:** Tailscale app → Account → Use custom control server.

### Client apps

| Platform | App |
| --- | --- |
| Windows / Mac | [tailscale.com/download](https://tailscale.com/download) |
| Linux | `curl -fsSL https://tailscale.com/install.sh \| sh` |
| iOS / Android | Tailscale app from App Store / Play Store |

### Useful commands

```bash
# List all registered devices
docker exec headscale headscale nodes list

# List users
docker exec headscale headscale users list

# Revoke a device
docker exec headscale headscale nodes delete --identifier <id>

# Generate new pre-auth key
docker exec headscale headscale preauthkeys create --user alice --reusable --expiration 72h
```

---

## openvpn — OpenVPN Server

Best when employees are behind restrictive corporate or hotel firewalls. OpenVPN is widely supported by corporate network policies that block WireGuard. Uses the `kylemanna/openvpn` community image — no user limit.

### First-time setup

OpenVPN requires a one-time PKI initialisation before the container can start.

**1. Create your `.env`**

```bash
cp openvpn/.env.example openvpn/.env
# edit OPENVPN_HOST to your server's public hostname or IP
```

**2. Generate server config**

```bash
docker run --rm \
  -v $(pwd)/data/openvpn:/etc/openvpn \
  kylemanna/openvpn ovpn_genconfig -u udp://YOUR_HOST
```

**3. Initialise PKI (sets a CA passphrase — keep it safe)**

```bash
docker run --rm -it \
  -v $(pwd)/data/openvpn:/etc/openvpn \
  kylemanna/openvpn ovpn_initpki
```

**4. Open firewall**

```bash
sudo ufw allow 1194/udp
```

**5. Start**

```bash
./homeserver.sh dev up openvpn
```

### Add an employee

```bash
# Create client cert (no password on the cert itself)
docker run --rm -it \
  -v $(pwd)/data/openvpn:/etc/openvpn \
  kylemanna/openvpn easyrsa build-client-full alice nopass

# Export .ovpn config file — send this file to the employee
docker run --rm \
  -v $(pwd)/data/openvpn:/etc/openvpn \
  kylemanna/openvpn ovpn_getclient alice > alice.ovpn
```

### Revoke an employee

```bash
docker run --rm -it \
  -v $(pwd)/data/openvpn:/etc/openvpn \
  kylemanna/openvpn ovpn_revokeclient alice
```

### Client apps

| Platform | App |
| --- | --- |
| Windows | OpenVPN Connect or OpenVPN GUI |
| Mac | Tunnelblick or OpenVPN Connect |
| Linux | `sudo apt install openvpn` then `sudo openvpn --config alice.ovpn` |
| iOS / Android | OpenVPN Connect from App Store / Play Store |

Employees import the `.ovpn` file into their app — that's it.

---

## Nginx proxy entries (prod)

Add these proxy hosts in Nginx Proxy Manager:

| Domain | Forward to | Port |
| --- | --- | --- |
| `vpn.yourdomain.com` | `wg-easy` | `51821` |
| `headscale.yourdomain.com` | `headscale` | `8080` |
| `headscale-admin.yourdomain.com` | `headscale-admin` | `80` |

For headscale, also enable WebSockets in the NPM proxy host settings (headscale uses long-polling).

---

## Firewall

```bash
# wg-easy
sudo ufw allow 51820/udp

# headscale — no extra ports needed if behind nginx
# (headscale uses your existing 443 via nginx)

# openvpn
sudo ufw allow 1194/udp
```

---

[← Services Reference](11-services-reference.md) | [Home](../setup.md)
