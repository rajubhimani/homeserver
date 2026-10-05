#!/usr/bin/env python3
"""In-cluster watchdog (docs/17 "Watchdog"): self-heals the Cloudflare tunnel and
alerts on cluster trouble, so nobody has to ask.

1. Tunnel. cloudflared's own readiness only counts its LOCAL connections; twice on
   2026-10-05 Cloudflare's edge had silently dropped them (public requests got
   `530 / error code: 1033`) while it still reported 4 ready. Docker had a watchdog
   for exactly that (services/cloudflared/watchdog.sh); the Kubernetes port skipped
   it on the wrong belief that the liveness probe covers it. This one probes the
   public URL from this pod AND from several places around the world (check-host.net,
   free public API), because a single vantage can pass through one Cloudflare edge
   while the others fail. It restarts cloudflared only when the origin (nginx-plain)
   is confirmed fine, and rate-limits itself.
2. Cluster. The same checks as `cluster.py verify` (pods, ArgoCD, databases, backups),
   every few minutes; ntfy tells you when one starts failing and when it recovers.
   (Docker's Uptime Kuma container monitors did this and are dead on Kubernetes.)

Standard library only. The decision functions are pure, so tests can run them.
"""

from __future__ import annotations

import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field

# ── decisions (pure) ─────────────────────────────────────────────────────


@dataclass
class TunnelState:
    consecutive_down: int = 0
    last_restart: float = 0.0
    restarts: list = field(default_factory=list)
    announced_down: bool = False
    origin_alerted: bool = False
    limit_alerted: bool = False

    def reset(self) -> None:
        self.consecutive_down, self.announced_down, self.origin_alerted, self.limit_alerted = 0, False, False, False


@dataclass
class Observation:
    replicas: int            # cloudflared's desired replicas (0 = stopped on purpose)
    origin_ok: bool          # nginx-plain answers inside the cluster
    local_ok: bool | None    # the public URL from this pod (None = not measured)
    vantage_ok: int = 0      # worldwide probes that got a real answer
    vantage_total: int = 0   # worldwide probes that gave a usable result


def tunnel_decision(st: TunnelState, obs: Observation, now: float, *, threshold: int = 3, cooldown: float = 600,
                    max_per_hour: int = 3, min_vantage: int = 3, fail_fraction: float = 0.5) -> list[tuple[str, str]]:
    """-> [("restart", why) | ("notify", text)]. Restart only when the public path is down
    `threshold` rounds in a row, the origin is fine, the cooldown has passed and the hourly
    limit isn't used up. Without enough worldwide results nothing is concluded from them."""
    acts: list[tuple[str, str]] = []
    if obs.replicas < 1:  # stopped on purpose (a rebuild): never start or restart it
        st.reset()
        return acts
    ext_down = obs.vantage_total >= min_vantage and (obs.vantage_total - obs.vantage_ok) / obs.vantage_total >= fail_fraction
    down = ext_down or obs.local_ok is False
    evidence = (f"{obs.vantage_total - obs.vantage_ok}/{obs.vantage_total} outside probes failed"
                + ("" if obs.local_ok is None else ", the public URL " + ("answers" if obs.local_ok else "fails") + " from inside"))
    if not down:
        if st.announced_down:
            acts.append(("notify", "Tunnel recovered: public sites answer again."))
        elif st.origin_alerted:
            acts.append(("notify", "Origin (nginx-plain) answers again."))
        st.reset()
        return acts
    st.consecutive_down += 1
    if not obs.origin_ok:  # nginx/Traefik broken: restarting the tunnel can't help
        if not st.origin_alerted:
            acts.append(("notify", f"Public sites are down ({evidence}) but the origin (nginx-plain) is down too. "
                                   "Not restarting the tunnel: this is not a stale tunnel. Check nginx-plain and Traefik."))
        st.origin_alerted = True
        return acts
    if st.consecutive_down < threshold:
        return acts
    st.restarts = [t for t in st.restarts if now - t < 3600]
    if len(st.restarts) >= max_per_hour:
        if not st.limit_alerted:
            acts.append(("notify", f"Public sites still down ({evidence}) after {max_per_hour} restarts this hour. "
                                   "Not restarting again: needs a human (Cloudflare incident? cloudflarestatus.com)."))
        st.limit_alerted = True
        return acts
    if now - st.last_restart < cooldown:
        return acts
    st.restarts.append(now)
    st.last_restart, st.announced_down, st.consecutive_down = now, True, 0
    acts.append(("restart", evidence))
    acts.append(("notify", f"Public sites were down ({evidence}); the origin is fine. Restarted cloudflared."))
    return acts


@dataclass
class ClusterState:
    count: dict = field(default_factory=dict)      # check -> consecutive failing rounds
    announced: set = field(default_factory=set)


def cluster_decision(st: ClusterState, results: list[tuple[str, bool, str]], need: int = 2) -> list[str]:
    """Notifications for checks that fail `need` rounds in a row (so a restart or a rollout
    doesn't page you) and for the ones that recover."""
    failing = {n: d for n, ok, d in results if not ok}
    st.count = {n: st.count.get(n, 0) + 1 for n in failing}
    new = [n for n, c in st.count.items() if c >= need and n not in st.announced]
    back = sorted(n for n in st.announced if n not in failing)
    st.announced = (st.announced | set(new)) - set(back)
    msgs = []
    if new:
        msgs.append("Cluster check failing: " + "; ".join(f"{n}: {failing[n] or 'failed'}" for n in sorted(new)))
    if back:
        msgs.append("Recovered: " + ", ".join(back))
    return msgs


# ── I/O ──────────────────────────────────────────────────────────────────

SA = "/var/run/secrets/kubernetes.io/serviceaccount"
API_PATHS = {
    ("nodes",): "/api/v1/nodes",
    ("pods", "-A"): "/api/v1/pods",
    ("applications.argoproj.io", "-n", "argocd"): "/apis/argoproj.io/v1alpha1/namespaces/argocd/applications",
    ("clusters.postgresql.cnpg.io", "-A"): "/apis/postgresql.cnpg.io/v1/clusters",
    ("mariadbs.k8s.mariadb.com", "-A"): "/apis/k8s.mariadb.com/v1alpha1/mariadbs",
    ("backupstoragelocations.velero.io", "-n", "velero"): "/apis/velero.io/v1/namespaces/velero/backupstoragelocations",
    ("backups.velero.io", "-n", "velero"): "/apis/velero.io/v1/namespaces/velero/backups",
    ("backups.postgresql.cnpg.io", "-A"): "/apis/postgresql.cnpg.io/v1/backups",
    ("deployments", "-n", "apps"): "/apis/apps/v1/namespaces/apps/deployments",
}


def log(msg: str) -> None:
    print(time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), msg, flush=True)


class Kube:
    def __init__(self) -> None:
        self.base = "https://kubernetes.default.svc"
        self.ctx = ssl.create_default_context(cafile=f"{SA}/ca.crt")

    def call(self, method: str, path: str, body: dict | None = None, ctype: str = "application/json") -> dict:
        with open(f"{SA}/token") as f:
            token = f.read().strip()
        req = urllib.request.Request(self.base + path, method=method, data=json.dumps(body).encode() if body else None,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": ctype, "Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=20, context=self.ctx) as r:
            return json.load(r)

    def kg(self, *args: str) -> list[dict]:
        """The `kubectl get` helper cluster.py verify uses, over the API (read-only)."""
        try:
            return self.call("GET", API_PATHS[args]).get("items", [])
        except urllib.error.HTTPError as e:
            if e.code == 404:  # CRD not installed
                return []
            raise

    def restart(self, namespace: str, deployment: str) -> None:
        """What `kubectl rollout restart` does: change the pod template's restartedAt annotation."""
        stamp = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        self.call("PATCH", f"/apis/apps/v1/namespaces/{namespace}/deployments/{deployment}",
                  {"spec": {"template": {"metadata": {"annotations": {"kubectl.kubernetes.io/restartedAt": stamp}}}}},
                  "application/strategic-merge-patch+json")


def http_status(url: str, headers: dict | None = None, timeout: float = 15) -> int:
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception:  # noqa: BLE001 - any network failure is "no answer"
        return 0


def vantage_probe(url: str, max_nodes: int = 6, wait: float = 30) -> tuple[int, int]:
    """(answered, usable) from check-host.net's public API (check-host.net/about/api): the URL
    fetched from nodes in many countries. A result is good when the page answers with < 500
    (a redirect or 401 is fine); Cloudflare's tunnel error is 530."""
    try:
        start = urllib.request.Request(f"https://check-host.net/check-http?host={urllib.parse.quote(url, safe='')}&max_nodes={max_nodes}",
                                       headers={"Accept": "application/json"})
        with urllib.request.urlopen(start, timeout=20) as r:
            rid = json.load(r)["request_id"]
        deadline, res = time.time() + wait, {}
        while time.time() < deadline:
            time.sleep(5)
            with urllib.request.urlopen(urllib.request.Request(f"https://check-host.net/check-result/{rid}",
                                                              headers={"Accept": "application/json"}), timeout=20) as r:
                res = json.load(r)
            if res and all(v is not None for v in res.values()):
                break
        ok = total = 0
        for v in res.values():
            attempt = v[0] if v else None
            if isinstance(attempt, list) and attempt and attempt[0] in (0, 1):
                total += 1
                code = attempt[3] if len(attempt) > 3 else None
                ok += int(attempt[0] == 1 and str(code).isdigit() and int(code) < 500)
        return ok, total
    except Exception as e:  # noqa: BLE001 - an unreachable checker means "no information", never "down"
        log(f"vantage probe unavailable: {e}")
        return 0, 0


def notify(text: str, title: str = "homeserver watchdog", priority: str = "high") -> None:
    url, token = os.environ.get("NTFY_URL"), os.environ.get("NTFY_TOKEN")
    log(f"NOTIFY: {text}")
    if not url:
        return
    headers = {"Title": title, "Priority": priority, "Tags": "warning"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    try:
        urllib.request.urlopen(urllib.request.Request(url, data=text.encode(), headers=headers, method="POST"), timeout=15).read()
    except Exception as e:  # noqa: BLE001
        log(f"ntfy failed: {e}")


def main(argv: list[str]) -> int:
    dry = "--dry-run" in argv or os.environ.get("WATCHDOG_DRY_RUN") == "1"
    once = "--once" in argv
    conf = json.load(open(os.environ.get("WATCHDOG_CONFIG", "/config/watchdog.json")))
    domain, ns, dep = conf["domain"], conf.get("namespace", "apps"), conf.get("deployment", "cloudflared")
    interval = int(os.environ.get("INTERVAL", "90"))
    cluster_every = int(os.environ.get("CLUSTER_EVERY", "5"))
    kube = Kube()
    tstate, cstate = TunnelState(), ClusterState()
    errors, loop = 0, 0
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import verify  # shipped next to this file; the same checks as `cluster.py verify`

    log(f"watchdog up: {domain}, every {interval}s, cluster checks every {cluster_every} rounds{' (dry run)' if dry else ''}")
    while True:
        try:
            d = kube.call("GET", f"/apis/apps/v1/namespaces/{ns}/deployments/{dep}")
            replicas = (d.get("spec") or {}).get("replicas", 1)
            origin_ok = 0 < http_status("http://nginx-plain/", {"Host": domain}) < 500
            local_ok = 0 < http_status(f"https://{domain}/") < 500
            ok, total = vantage_probe(f"https://{domain}/")
            obs = Observation(replicas, origin_ok, local_ok, ok, total)
            log(f"tunnel: replicas={replicas} origin={origin_ok} local={local_ok} outside={ok}/{total}")
            for kind, text in tunnel_decision(tstate, obs, time.time()):
                if dry:
                    log(f"DRY RUN, would {kind}: {text}")
                elif kind == "restart":
                    kube.restart(ns, dep)
                    log(f"restarted {dep}: {text}")
                elif kind == "notify":
                    notify(text)
            if loop % cluster_every == 0:
                results = verify.verify_checks(set(conf["run"]), set(conf["ported"]), kube.kg, None, None, None)
                for msg in cluster_decision(cstate, results):
                    if dry:
                        log(f"DRY RUN, would notify: {msg}")
                    else:
                        notify(msg, priority="default")
                log("cluster: " + ", ".join(f"{n}={'ok' if good else 'FAIL'}" for n, good, _ in results))
            errors = 0
        except Exception as e:  # noqa: BLE001 - keep watching; tell the owner if it persists
            errors += 1
            log(f"round failed ({errors}): {type(e).__name__}: {e}")
            if errors == 10 and not dry:
                notify(f"The watchdog itself has failed 10 rounds in a row: {type(e).__name__}: {e}", priority="high")
        loop += 1
        try:  # the liveness probe reads this: a stuck loop gets the pod restarted
            with open("/tmp/heartbeat", "w") as hb:
                hb.write(str(time.time()))
        except OSError:
            pass
        if once:
            return 0
        time.sleep(interval)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
