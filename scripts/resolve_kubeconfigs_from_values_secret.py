#!/usr/bin/env python3
"""Resolve hub (primary) and DR kubeconfig paths from values-secret YAML.

Secret names match values-secret.yaml.template:
  - ocp-primary-cluster-kubeconfig  -> production / hub cluster
  - ocp-dr-cluster-kubeconfig       -> DR cluster (hub discovery peer)

Usage:
  resolve_kubeconfigs_from_values_secret.py prod
  resolve_kubeconfigs_from_values_secret.py dr
  resolve_kubeconfigs_from_values_secret.py --check
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required (pip install pyyaml)", file=sys.stderr)
    sys.exit(2)


SECRET_PRIMARY = "ocp-primary-cluster-kubeconfig"
SECRET_DR = "ocp-dr-cluster-kubeconfig"
FIELD_KUBECONFIG = "kubeconfig"


def values_secret_path() -> Path:
    explicit = os.environ.get("VALUES_SECRET", "").strip()
    if explicit:
        return Path(os.path.expanduser(explicit))
    pattern = os.environ.get("PATTERN_NAME", "netapp-dr-starter-kit").strip()
    return Path.home() / f"values-secret-{pattern}.yaml"


def field_path(secrets_doc: dict, secret_name: str, field_name: str = FIELD_KUBECONFIG) -> str | None:
    for entry in secrets_doc.get("secrets") or []:
        if entry.get("name") != secret_name:
            continue
        for field in entry.get("fields") or []:
            if field.get("name") != field_name:
                continue
            raw = field.get("path")
            if raw:
                return os.path.expanduser(str(raw).strip())
    return None


def load_paths() -> tuple[str | None, str | None, Path]:
    path = values_secret_path()
    if not path.is_file():
        return None, None, path
    with path.open(encoding="utf-8") as fh:
        doc = yaml.safe_load(fh) or {}
    prod = field_path(doc, SECRET_PRIMARY)
    dr = field_path(doc, SECRET_DR)
    return prod, dr, path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "which",
        nargs="?",
        choices=("prod", "dr", "primary"),
        help="Which kubeconfig path to print (primary is an alias for prod)",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 0 if both paths are configured and files exist; else exit 1",
    )
    args = parser.parse_args()

    prod, dr, secret_path = load_paths()
    if args.check:
        missing = []
        if not prod:
            missing.append(f"{SECRET_PRIMARY} (field {FIELD_KUBECONFIG}.path)")
        elif not Path(prod).is_file():
            missing.append(f"{SECRET_PRIMARY} path not found: {prod}")
        if not dr:
            missing.append(f"{SECRET_DR} (field {FIELD_KUBECONFIG}.path)")
        elif not Path(dr).is_file():
            missing.append(f"{SECRET_DR} path not found: {dr}")
        if missing:
            print(f"{secret_path}:", file=sys.stderr)
            for line in missing:
                print(f"  - {line}", file=sys.stderr)
            return 1
        return 0

    if not args.which:
        parser.error("which is required unless --check is set")

    which = "prod" if args.which == "primary" else args.which
    chosen = prod if which == "prod" else dr
    if not chosen:
        print(
            f"No kubeconfig path for {SECRET_PRIMARY if which == 'prod' else SECRET_DR} "
            f"in {secret_path}",
            file=sys.stderr,
        )
        return 1
    print(chosen)
    return 0


if __name__ == "__main__":
    sys.exit(main())
