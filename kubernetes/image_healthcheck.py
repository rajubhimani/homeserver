#!/usr/bin/env python3
"""Print an image's own HEALTHCHECK, read from its registry without pulling.

    uv run kubernetes/image_healthcheck.py ghcr.io/mealie-recipes/mealie:v3.28.0
    uv run kubernetes/image_healthcheck.py --yaml <image>   # as an override image_healthcheck block

Kubernetes ignores image HEALTHCHECKs, so a container that relies on one gets
it copied into kubernetes/overrides/<svc>.yaml (image_healthcheck). When the
image is pulled locally, `docker image inspect` gives the same; this reads the
raw image config from the registry (Docker Hub, ghcr.io, ...), because the
OCI form `docker buildx imagetools inspect` prints drops the healthcheck.
"""

from __future__ import annotations

import json
import re
import sys
import urllib.request

import yaml

ACCEPT = ", ".join([
    "application/vnd.oci.image.index.v1+json",
    "application/vnd.docker.distribution.manifest.list.v2+json",
    "application/vnd.oci.image.manifest.v1+json",
    "application/vnd.docker.distribution.manifest.v2+json",
])


def parse(ref: str) -> tuple[str, str, str]:
    """-> (registry host, repository, tag or digest)"""
    name, _, digest = ref.partition("@")
    tag = "latest"
    if not digest and re.search(r":[^/]+$", name):
        name, tag = name.rsplit(":", 1)
    first = name.split("/", 1)[0]
    if "." in first or ":" in first or first == "localhost":
        host, repo = first, name.split("/", 1)[1]
    else:
        host, repo = "registry-1.docker.io", name if "/" in name else f"library/{name}"
    return host, repo, digest or tag


def get(url: str, token: str | None, accept: str = ACCEPT) -> tuple[bytes, dict]:
    req = urllib.request.Request(url, headers={"Accept": accept, **({"Authorization": f"Bearer {token}"} if token else {})})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read(), dict(r.headers)


def token_for(host: str, repo: str) -> str | None:
    """Anonymous pull token from the registry's WWW-Authenticate challenge."""
    try:
        get(f"https://{host}/v2/", None)
        return None
    except urllib.error.HTTPError as e:
        ch = e.headers.get("WWW-Authenticate", "")
    realm = re.search(r'realm="([^"]+)"', ch)
    service = re.search(r'service="([^"]+)"', ch)
    if not realm:
        return None
    url = f"{realm.group(1)}?scope=repository:{repo}:pull" + (f"&service={service.group(1)}" if service else "")
    body, _ = get(url, None, "application/json")
    d = json.loads(body)
    return d.get("token") or d.get("access_token")


def healthcheck(ref: str, platform: str = "linux/amd64") -> dict | None:
    host, repo, ref_ = parse(ref)
    tok = token_for(host, repo)
    body, _ = get(f"https://{host}/v2/{repo}/manifests/{ref_}", tok)
    m = json.loads(body)
    if "manifests" in m:  # index / manifest list: pick the platform
        os_, arch = platform.split("/")
        d = next(x["digest"] for x in m["manifests"]
                 if x.get("platform", {}).get("os") == os_ and x.get("platform", {}).get("architecture") == arch)
        m = json.loads(get(f"https://{host}/v2/{repo}/manifests/{d}", tok)[0])
    cfg = json.loads(get(f"https://{host}/v2/{repo}/blobs/{m['config']['digest']}", tok, "*/*")[0])
    return (cfg.get("config") or {}).get("Healthcheck")


def as_override(hc: dict) -> dict:
    """Docker's form (ns durations) -> the override's image_healthcheck block."""
    out = {"test": hc["Test"]}
    for ki, ko in (("Interval", "interval"), ("Timeout", "timeout"), ("StartPeriod", "start_period"),
                   ("StartInterval", "start_interval")):
        if hc.get(ki):
            out[ko] = f"{hc[ki] // 1_000_000_000}s"
    if hc.get("Retries"):
        out["retries"] = hc["Retries"]
    return out


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(args) != 1:
        sys.exit(__doc__)
    hc = healthcheck(args[0])
    if hc is None:
        print("(no HEALTHCHECK in this image)")
        return 1
    print(yaml.safe_dump({"image_healthcheck": as_override(hc)}, sort_keys=False, width=200) if "--yaml" in sys.argv
          else json.dumps(hc))
    return 0


if __name__ == "__main__":
    sys.exit(main())
