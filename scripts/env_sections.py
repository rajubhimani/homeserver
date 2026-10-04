#!/usr/bin/env python3
"""Arrange a service's .env / .env.example into three labelled sections:

  Common       values both Docker Compose and Kubernetes use (most of the file)
  Docker only  values Kubernetes doesn't read (DATA_ROOT; values the generator
               replaces on Kubernetes, e.g. landing's UPSTREAM_SUFFIX)
  Kubernetes   comments only: what kubernetes/generate.py sets instead, so the
               difference is visible. Nothing to comment/uncomment: one .env
               works for both runtimes.

Only order and the section headers change; every key keeps its value and the
comment lines directly above it. Idempotent: re-running rebuilds the sections.

    uv run scripts/env_sections.py                 # all .env.example files
    uv run scripts/env_sections.py --real          # the real .env files too
    uv run scripts/env_sections.py --check         # exit 1 if any file needs it
"""

from __future__ import annotations

import argparse
import os
import re
import shutil
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
SERVICES = REPO / "services"
OVERRIDES = REPO / "kubernetes" / "overrides"
KEY = re.compile(r"^([A-Za-z_][A-Za-z0-9_]*)=")
BAR = "═" * 60
H_COMMON = f"# {BAR}\n# Common: Docker Compose and Kubernetes\n# {BAR}"
H_DOCKER = f"# {BAR}\n# Docker Compose only (Kubernetes ignores these, or uses the values below)\n# {BAR}"
H_K8S = f"# {BAR}\n# Kubernetes\n# {BAR}"
HEADER = re.compile(r"^# ═+\n# (Common|Docker Compose only|Kubernetes)[^\n]*\n# ═+\n?", re.M)
DOCKER_ONLY = {"DATA_ROOT"}


def k8s_env(svc: str) -> dict[str, str]:
    """{KEY: value} the generator sets on Kubernetes for this service."""
    f = OVERRIDES / f"{svc}.yaml"
    out: dict[str, str] = {}
    if f.is_file():
        for co in ((yaml.safe_load(f.read_text()) or {}).get("containers") or {}).values():
            out.update({k: str(v) for k, v in (co.get("env") or {}).items()})
    return out


def blocks(text: str) -> list[tuple[str | None, list[str]]]:
    """Split into blocks: (key, lines) where lines are the comment lines
    directly above a KEY= line plus the line itself; (None, lines) for the
    rest (free comments, blank lines)."""
    out: list[tuple[str | None, list[str]]] = []
    pending: list[str] = []
    for line in text.splitlines():
        m = KEY.match(line)
        if m:
            out.append((m.group(1), pending + [line]))
            pending = []
        elif line.startswith("#"):
            pending.append(line)
        else:  # blank line ends an attached comment block
            if pending:
                out.append((None, pending))
                pending = []
            out.append((None, [line]))
    if pending:
        out.append((None, pending))
    return out


def arrange(svc: str, text: str) -> str:
    body = HEADER.sub("", text)
    # drop the generated Kubernetes section (rebuilt below)
    body = re.sub(r"\n*# Nothing to change for Kubernetes:.*\Z", "", body, flags=re.S)
    k8s = k8s_env(svc)
    docker_keys = DOCKER_ONLY | set(k8s)
    common, docker = [], []
    for key, lines in blocks(body):
        (docker if key in docker_keys else common).append(lines)
    common_txt = re.sub(r"\n{3,}", "\n\n", "\n".join(l for b in common for l in b)).strip("\n")
    docker_txt = "\n\n".join("\n".join(b) for b in docker).strip("\n")
    k8s_lines = ["# Nothing to change for Kubernetes: cluster.py secrets loads this whole file",
                 f"# as Secret {svc}-env, and kubernetes/generate.py sets what differs:"]
    k8s_lines += [f"#   {k}={v}" for k, v in sorted(k8s.items())] or ["#   (nothing differs for this service)"]
    if "DATA_ROOT" in {k for k, _ in blocks(body)}:
        k8s_lines.append("# DATA_ROOT is replaced by the service's volumes (storage classes fast/bulk).")
    parts = [H_COMMON, common_txt]
    if docker_txt:
        parts += ["", H_DOCKER, docker_txt]
    parts += ["", H_K8S, "\n".join(k8s_lines)]
    return "\n".join(parts).rstrip("\n") + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--real", action="store_true", help="also arrange the real .env files")
    ap.add_argument("--check", action="store_true", help="report files that would change, change nothing")
    ap.add_argument("services", nargs="*")
    a = ap.parse_args()
    names = [".env.example"] + ([".env"] if a.real else [])
    stale = []
    for d in sorted(p for p in SERVICES.iterdir() if p.is_dir()):
        if a.services and d.name not in a.services:
            continue
        for n in names:
            f = d / n
            if not f.is_file():
                continue
            old = f.read_text()
            new = arrange(d.name, old)
            before = {k: l[-1] for k, l in blocks(HEADER.sub("", old)) if k}
            after = {k: l[-1] for k, l in blocks(new) if k}
            if before != after:
                sys.exit(f"{f}: keys/values would change; refusing")
            if new != old:
                stale.append(str(f.relative_to(REPO)))
                if not a.check:
                    # Whole-file replace (readers never see a half-written
                    # .env), keeping the original permissions.
                    tmp = f.with_name(f.name + ".arranging")
                    tmp.write_text(new)
                    shutil.copymode(f, tmp)
                    os.replace(tmp, f)
    if a.check:
        print("\n".join(stale) or "all arranged")
        return 1 if stale else 0
    print(f"arranged {len(stale)} file(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
