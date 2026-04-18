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

```bash
sudo mkdir -p /mnt/seagate/{nextcloud,immich,postgres-nextcloud,postgres-immich}
sudo chown -R $USER:$USER /mnt/seagate
```

---

[Home](../setup.md) | [Next: Docker + Network →](02-docker-network.md)
