#!/usr/bin/env python3
"""Patch the hub Pattern Application so discovery-injected helm parameters on child Apps are not reverted."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
from typing import Any, Dict, List

DISCOVERY_MANAGED_CHILD_APP_NAMES = frozenset({"crossplane-aws-infra", "dr-dns-reconciler"})
_DISCOVERY_PARENT_HELM_PARAM_SOURCE_INDEX_CAP = 20
_RESPECT_IGNORE_DIFFERENCES_SYNC_OPTION = "RespectIgnoreDifferences=true"


def _discovery_parent_json_pointers() -> List[str]:
    n = _DISCOVERY_PARENT_HELM_PARAM_SOURCE_INDEX_CAP
    ptrs: List[str] = (
        [
            "/spec/source/helm/parameters",
            "/spec/source/helm/valueFiles",
            "/spec/source/helm/ignoreMissingValueFiles",
        ]
        + [f"/spec/sources/{i}/helm/parameters" for i in range(n)]
        + [f"/spec/sources/{i}/helm/valueFiles" for i in range(n)]
        + [f"/spec/sources/{i}/helm/ignoreMissingValueFiles" for i in range(n)]
    )
    ptrs += [
        "/metadata/annotations/argocd.argoproj.io~1tracking-id",
        "/metadata/annotations/argocd.argoproj.io~1refresh",
        "/metadata/annotations/argocd.argoproj.io~1instance",
        "/metadata/annotations/notified.notifications.argoproj.io~1notified-on",
        "/metadata/labels/app.kubernetes.io~1instance",
    ]
    return sorted(dict.fromkeys(ptrs))


def _discovery_parent_ignore_entries() -> List[Dict[str, Any]]:
    ptrs = _discovery_parent_json_pointers()
    jqs = ['.metadata.annotations["kubectl.kubernetes.io/last-applied-configuration"]']
    return [
        {
            "group": "argoproj.io",
            "kind": "Application",
            "name": n,
            "jsonPointers": list(ptrs),
            "jqPathExpressions": list(jqs),
        }
        for n in sorted(DISCOVERY_MANAGED_CHILD_APP_NAMES)
    ]


def _ignore_entry_key(entry: Dict[str, Any]) -> tuple:
    return (
        str(entry.get("group") or ""),
        str(entry.get("kind") or ""),
        str(entry.get("name") or ""),
    )


def merge_parent_ignore_differences(app: dict) -> bool:
    spec = app.setdefault("spec", {})
    raw_existing: List[Any] = list(spec.get("ignoreDifferences") or [])
    wants = _discovery_parent_ignore_entries()
    out: List[Any] = []
    for entry in raw_existing:
        if not isinstance(entry, dict):
            out.append(entry)
            continue
        if (
            entry.get("group") == "argoproj.io"
            and entry.get("kind") == "Application"
            and not (entry.get("name") or "").strip()
            and not (entry.get("namespace") or "").strip()
        ):
            jqs = entry.get("jqPathExpressions") or []
            if any("netappDrDiscoveryJson" in str(j) for j in jqs):
                continue
        if (
            entry.get("group") == "argoproj.io"
            and entry.get("kind") == "Application"
            and (entry.get("name") or "") in DISCOVERY_MANAGED_CHILD_APP_NAMES
        ):
            continue
        out.append(entry)
    changed = len(out) != len(raw_existing)
    for want in wants:
        key = _ignore_entry_key(want)
        if not any(isinstance(e, dict) and _ignore_entry_key(e) == key for e in out):
            out.append(dict(want))
            changed = True
    if changed:
        spec["ignoreDifferences"] = out
    return changed


def ensure_respect_ignore_differences(app: dict) -> bool:
    spec = app.setdefault("spec", {})
    sp = spec.setdefault("syncPolicy", {})
    opts = list(sp.get("syncOptions") or [])
    if _RESPECT_IGNORE_DIFFERENCES_SYNC_OPTION in opts:
        return False
    opts.append(_RESPECT_IGNORE_DIFFERENCES_SYNC_OPTION)
    sp["syncOptions"] = opts
    return True


def main() -> int:
    ns = os.environ.get("ARGOCD_PARENT_APPLICATION_NAMESPACE", "vp-gitops").strip()
    pattern = os.environ.get("GLOBAL_PATTERN", "netapp-dr-starter-kit").strip()
    cg = os.environ.get("CLUSTER_GROUP_NAME", "hub").strip()
    name = os.environ.get("ARGOCD_PARENT_APPLICATION_NAME", "").strip() or f"{pattern}-{cg}"
    kubeconfig = os.environ.get("KUBECONFIG", "").strip()
    oc = ["oc"]
    if kubeconfig:
        oc.extend(["--kubeconfig", kubeconfig])
    raw = subprocess.run(
        [*oc, "get", "application.argoproj.io", name, "-n", ns, "-o", "json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    app = json.loads(raw)
    idiff_changed = merge_parent_ignore_differences(app)
    syncopt_changed = ensure_respect_ignore_differences(app)
    if not idiff_changed and not syncopt_changed:
        print(f"No change needed for {ns}/{name}")
        return 0
    patch_spec: Dict[str, Any] = {}
    if idiff_changed:
        patch_spec["ignoreDifferences"] = app["spec"]["ignoreDifferences"]
    if syncopt_changed:
        patch_spec["syncPolicy"] = {"syncOptions": app["spec"]["syncPolicy"]["syncOptions"]}
    patch_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"spec": patch_spec}, f)
            patch_path = f.name
        r = subprocess.run(
            [*oc, "patch", "application.argoproj.io", name, "-n", ns, "--type=merge", "--patch-file", patch_path],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            print(r.stderr or r.stdout, file=sys.stderr)
            return 1
    finally:
        if patch_path:
            try:
                os.unlink(patch_path)
            except OSError:
                pass
    print(f"Patched {ns}/{name} (ignoreDifferences={idiff_changed}, RespectIgnoreDifferences={syncopt_changed})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
