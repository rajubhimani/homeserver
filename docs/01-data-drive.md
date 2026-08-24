# 01 — Prepare Data Drive

[Home](../setup.md) | [Next: Docker + Network →](02-docker-network.md)

---

Format your data drive to ext4 and set it up for persistent mounting.

## Identify the drive

```bash
lsblk
```

## Format

> ⚠️ This is destructive — back up anything on the drive first.

```bash
sudo mkfs.ext4 -L "seagate" /dev/sdX
```

## Create mount point and get UUID

```bash
sudo mkdir -p /mnt/seagate
sudo blkid | grep seagate
```

## Add to /etc/fstab

```bash
sudo nano /etc/fstab
```

Add this line (replace UUID with yours):

```text
UUID=your-uuid-here  /mnt/seagate  ext4  defaults,nofail,x-systemd.device-timeout=10  0  2
```

## Apply and verify

```bash
sudo mount -a
ls /mnt/seagate
```

## Create folder structure

This drive is for your own external data (e.g. files to expose via Nextcloud's
External Storage, or media for Jellyfin) — not for service state, which lives
under `service_data/` in the repo (bind mounts) or named Docker volumes
(Postgres/MariaDB/RabbitMQ). Create whatever subfolders suit your own data:

```bash
sudo chown -R $USER:$USER /mnt/seagate
```

---

[Home](../setup.md) | [Next: Docker + Network →](02-docker-network.md)
