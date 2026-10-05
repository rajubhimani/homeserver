"""Tier/group/service targets, resolved exactly as homeserver.py resolves them
(it's imported): 'up core' also means MIN, 'down core' only CORE, 'down all'
everything in reverse order, group:<name> from services.json. Shared by
generate.py (kubernetes/deploy/<env>.yaml's running list) and k8s.py."""

from __future__ import annotations

import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))
import homeserver as hs  # noqa: E402

TIERS = {
    "min": lambda: hs.SERVICES_MIN,
    "core": lambda: hs.SERVICES_MIN + hs.SERVICES_CORE,
    "daily": lambda: hs.SERVICES_MIN + hs.SERVICES_CORE + hs.SERVICES_DAILY,
    "browser": lambda: hs.SERVICES_MIN + hs.SERVICES_CORE + hs.SERVICES_DAILY + hs.SERVICES_BROWSER,
    "office": lambda: hs.SERVICES_MIN + hs.SERVICES_CORE + hs.SERVICES_DAILY + hs.SERVICES_BROWSER + hs.SERVICES_OFFICE,
    "automation-ai": lambda: (hs.SERVICES_MIN + hs.SERVICES_CORE + hs.SERVICES_DAILY + hs.SERVICES_BROWSER
                              + hs.SERVICES_OFFICE + hs.SERVICES_AUTOMATION_AI),
    "all": lambda: (hs.SERVICES_MIN + hs.SERVICES_CORE + hs.SERVICES_DAILY + hs.SERVICES_BROWSER + hs.SERVICES_OFFICE
                    + hs.SERVICES_AUTOMATION_AI + hs.SERVICES_EXTRA),
}
# 'down <tier>' stops only that tier (homeserver.py semantics); 'down all' everything.
DOWN_ONLY = {
    "min": lambda: hs.SERVICES_MIN, "core": lambda: hs.SERVICES_CORE, "daily": lambda: hs.SERVICES_DAILY,
    "browser": lambda: hs.SERVICES_BROWSER, "office": lambda: hs.SERVICES_OFFICE,
    "automation-ai": lambda: hs.SERVICES_AUTOMATION_AI, "all": TIERS["all"],
}


class TargetError(ValueError):
    pass


def resolve(tokens: list[str], action: str = "up") -> tuple[list[str], bool]:
    """-> (services in order, expanded): the same targets homeserver.py accepts."""
    out, expanded = [], False
    for tok in tokens:
        if action == "down" and tok in DOWN_ONLY:
            out += DOWN_ONLY[tok]()
            expanded = True
        elif tok in TIERS:
            out += TIERS[tok]()
            expanded = True
        elif tok.startswith("group:"):
            name = tok[len("group:"):]
            if name not in hs.SERVICE_GROUPS:
                raise TargetError(f"unknown group '{name}' (valid: {', '.join(sorted(hs.SERVICE_GROUPS))})")
            out += hs.SERVICE_GROUPS[name]
            expanded = True
        elif hs.is_valid_service(tok):
            out.append(tok)
        else:
            raise TargetError(f"unknown service or target '{tok}'")
    seen, ordered = set(), []
    for s in out:
        if s not in seen:
            seen.add(s)
            ordered.append(s)
    if action == "down" and "all" in tokens:
        ordered.reverse()  # like homeserver.py: stop in reverse order
    return ordered, expanded
