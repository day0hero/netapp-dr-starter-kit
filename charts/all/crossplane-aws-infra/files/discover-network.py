#!/usr/bin/env python3
"""
Discover OpenShift + AWS networking for Crossplane (hub and secondary).
Writes a ConfigMap data key discovery.json consumed by Helm lookup merge.
"""
from __future__ import annotations

import base64
import json
import os
import re
import subprocess
import sys
import tempfile
from typing import Any, Dict, List, Optional


def run_oc(kubeconfig: Optional[str], args: List[str]) -> str:
    env = os.environ.copy()
    if kubeconfig:
        env["KUBECONFIG"] = kubeconfig
    r = subprocess.run(["oc", *args], capture_output=True, text=True, env=env)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        raise RuntimeError(f"oc failed: {' '.join(args)}")
    return r.stdout.strip()


def run_aws_json(args: List[str]) -> Any:
    r = subprocess.run(["aws", *args], capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr, file=sys.stderr)
        raise RuntimeError(f"aws failed: {' '.join(args)}")
    return json.loads(r.stdout or "null")


def oc_json(kubeconfig: Optional[str], *args: str) -> Any:
    raw = run_oc(kubeconfig, ["get", *args, "-o", "json"])
    return json.loads(raw)


def discover_install_cidr(kubeconfig: Optional[str]) -> str:
    try:
        raw = run_oc(
            kubeconfig,
            [
                "get",
                "configmap",
                "cluster-config-v1",
                "-n",
                "kube-system",
                "-o",
                'jsonpath={.data.install-config}',
            ],
        )
        if not raw:
            return ""
        # install-config is YAML; extract machineNetwork[0].cidr without PyYAML
        m = re.search(r"machineNetwork:\s*\n\s*-\s*cidr:\s*(\S+)", raw)
        if m:
            return m.group(1).strip()
    except RuntimeError:
        pass
    return ""


def discover_cluster(kubeconfig: Optional[str], label: str) -> Dict[str, Any]:
    infra = oc_json(kubeconfig, "infrastructure", "cluster")
    st = infra.get("status") or {}
    plat = st.get("platformStatus") or {}
    aws = plat.get("aws") or {}
    region = (aws.get("region") or "").strip()
    infra_name = (st.get("infrastructureName") or "").strip()
    topology = (st.get("controlPlaneTopology") or "").strip()
    is_hcp = topology == "External"
    cluster_name = (infra.get("metadata") or {}).get("name") or infra_name
    if not region or not infra_name:
        raise RuntimeError(f"{label}: missing region or infrastructureName from Infrastructure")

    vpc_name = f"{infra_name}-vpc"
    cidr_override = discover_install_cidr(kubeconfig)

    vpcs = run_aws_json(
        [
            "ec2",
            "describe-vpcs",
            "--region",
            region,
            "--filters",
            f"Name=tag:Name,Values={vpc_name}",
            "--output",
            "json",
        ]
    )
    vpc_list = (vpcs or {}).get("Vpcs") or []
    if not vpc_list and is_hcp:
        tag_key = f"tag:sigs.k8s.io/cluster-api-provider-aws/cluster/{infra_name}"
        vpcs = run_aws_json(
            [
                "ec2",
                "describe-vpcs",
                "--region",
                region,
                "--filters",
                f"Name={tag_key},Values=owned",
                "--output",
                "json",
            ]
        )
        vpc_list = (vpcs or {}).get("Vpcs") or []
    if not vpc_list:
        raise RuntimeError(f"{label}: VPC not found (Name={vpc_name}, HCP={is_hcp})")

    vpc_id = vpc_list[0]["VpcId"]
    vpc_cidr = vpc_list[0].get("CidrBlock") or cidr_override
    if not vpc_cidr:
        raise RuntimeError(f"{label}: could not resolve VPC CIDR")

    if is_hcp:
        subnet_filters = [
            "Name=vpc-id,Values=" + vpc_id,
            "Name=tag:kubernetes.io/role/internal-elb,Values=1",
        ]
    else:
        subnet_filters = [
            "Name=vpc-id,Values=" + vpc_id,
            "Name=tag:sigs.k8s.io/cluster-api-provider-aws/role,Values=private",
            f"Name=tag:kubernetes.io/cluster/{infra_name},Values=owned",
            f"Name=tag:sigs.k8s.io/cluster-api-provider-aws/cluster/{infra_name},Values=owned",
        ]
    sn_args = ["ec2", "describe-subnets", "--region", region, "--output", "json"]
    for i in range(0, len(subnet_filters), 2):
        sn_args.extend(["--filters", subnet_filters[i], subnet_filters[i + 1]])
    sn = run_aws_json(sn_args)
    subnets = sorted((sn or {}).get("Subnets") or [], key=lambda s: s.get("SubnetId", ""))
    subnet_ids = [s["SubnetId"] for s in subnets if s.get("SubnetId")]
    if len(subnet_ids) < 2:
        raise RuntimeError(f"{label}: need >= 2 private subnets, found {len(subnet_ids)}")

    rt_ids: List[str] = []
    for sid in subnet_ids:
        rts = run_aws_json(
            [
                "ec2",
                "describe-route-tables",
                "--region",
                region,
                "--filters",
                "Name=association.subnet-id,Values=" + sid,
                f"Name=vpc-id,Values={vpc_id}",
                "--output",
                "json",
            ]
        )
        for rt in (rts or {}).get("RouteTables") or []:
            if rt.get("RouteTableId"):
                rt_ids.append(rt["RouteTableId"])
    route_table_ids = sorted(set(rt_ids))

    all_rt = run_aws_json(
        [
            "ec2",
            "describe-route-tables",
            "--region",
            region,
            "--filters",
            f"Name=vpc-id,Values={vpc_id}",
            "--output",
            "json",
        ]
    )
    all_route_table_ids = sorted({rt["RouteTableId"] for rt in (all_rt or {}).get("RouteTables") or [] if rt.get("RouteTableId")})

    ingress_domain = run_oc(
        kubeconfig,
        ["get", "ingress.config", "cluster", "-o", "jsonpath={.spec.domain}"],
    )
    base_domain = run_oc(
        kubeconfig,
        ["get", "dns.config", "cluster", "-o", "jsonpath={.spec.baseDomain}"],
    )

    return {
        "cluster_name": cluster_name.strip(),
        "region": region,
        "vpc_id": vpc_id,
        "vpc_cidr": vpc_cidr,
        "infra_name": infra_name,
        "is_hcp": is_hcp,
        "subnet_ids": subnet_ids,
        "route_table_ids": route_table_ids,
        "all_route_table_ids": all_route_table_ids,
        "ingress_domain": ingress_domain,
        "base_domain": base_domain,
    }


def fsx_name(cluster_name: str, region: str) -> str:
    return f"{cluster_name}-{region}-fsx"


def route53_lookup_zone_id(domain: str, region: str) -> str:
    if not domain:
        return ""
    out = subprocess.run(
        [
            "aws",
            "route53",
            "list-hosted-zones-by-name",
            "--dns-name",
            domain,
            "--query",
            f"HostedZones[?Name=='{domain}.'].Id",
            "--output",
            "text",
        ],
        capture_output=True,
        text=True,
        env={**os.environ, "AWS_DEFAULT_REGION": region},
    )
    if out.returncode != 0:
        print(out.stderr, file=sys.stderr)
        return ""
    line = (out.stdout or "").strip().split("\n", 1)[0].strip()
    if not line:
        return ""
    return line.replace("/hostedzone/", "")


def crossplane_zone_id(domain: str) -> str:
    """If Crossplane already created a public zone, read its AWS zone id from status."""
    safe = domain.replace(".", "-")
    name = f"dr-{safe}"
    try:
        raw = run_oc(
            None,
            [
                "get",
                "zone.route53.aws.upbound.io",
                name,
                "-n",
                os.environ.get("TARGET_NAMESPACE", "crossplane-system"),
                "-o",
                "json",
            ],
        )
        z = json.loads(raw)
        at = ((z.get("status") or {}).get("atProvider") or {})
        zid = (at.get("id") or "").strip()
        return zid.replace("/hostedzone/", "") if zid else ""
    except (RuntimeError, json.JSONDecodeError, KeyError):
        return ""


def apply_configmap(namespace: str, name: str, data: Dict[str, str]) -> None:
    obj = {
        "apiVersion": "v1",
        "kind": "ConfigMap",
        "metadata": {"name": name, "namespace": namespace},
        "data": data,
    }
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(obj, f)
        path = f.name
    try:
        subprocess.run(["oc", "apply", "-f", path, "--server-side", "--field-manager=discover-network"], check=True)
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


DISCOVERY_HELM_PARAM_LEGACY = "netappDrDiscoveryJson"
DISCOVERY_HELM_PARAM_B64 = "netappDrDiscoveryJsonB64"

# Child Application specs patched with netappDrDiscoveryJson(B64) drift from Git; the hub
# Pattern Application (app-of-apps) compares those CRs and shows OutOfSync unless we ignore
# helm.parameters on the child Applications discovery mutates.
#
# Argo CD implements jqPathExpressions as del(<expr>) (see argo-cd util/argo/normalizers/diff_normalizer.go);
# pipeline jq often fails or no-ops, and failures are skipped — so we use jsonPointers only.
# Omit namespace on ignore rules so Argo matches any namespace (patch.GetNamespace() == "").
# jsonPointers: discovery-injected helm.parameters; Argo-mutated helm.ignoreMissingValueFiles; and
# common Argo annotations on child Application CRs (~1 is RFC 6901 encoding for "/" in keys).
DISCOVERY_MANAGED_CHILD_APP_NAMES = frozenset({"crossplane-aws-infra", "dr-dns-reconciler"})


# Cover enough multisource indices for Helm blocks on child Applications (VP + OCI extras).
_DISCOVERY_PARENT_HELM_PARAM_SOURCE_INDEX_CAP = 20


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


def _stable_sorted_unique_pointers(ptrs: List[str]) -> List[str]:
    return sorted(dict.fromkeys(str(p) for p in ptrs if p))


def _discovery_parent_ignore_entries() -> List[Dict[str, Any]]:
    ptrs = _discovery_parent_json_pointers()
    # jqPathExpressions are reliable here (Argo diff normalizer); use for annotation keys that
    # are awkward in RFC6901 pointers (and for last-applied-configuration from kubectl apply).
    jqs = [
        '.metadata.annotations["kubectl.kubernetes.io/last-applied-configuration"]',
    ]
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


def _strip_application_for_server_replace(app: dict) -> None:
    """Drop read-only / noisy fields so oc replace is less likely to fight the apiserver."""
    app.pop("status", None)
    md = app.get("metadata")
    if isinstance(md, dict) and "managedFields" in md:
        del md["managedFields"]


def _strip_discovery_helm_params(helm: dict) -> None:
    params = helm.get("parameters")
    if not params:
        return
    drop = {DISCOVERY_HELM_PARAM_LEGACY, DISCOVERY_HELM_PARAM_B64}
    helm["parameters"] = [p for p in params if p.get("name") not in drop]


def _append_discovery_param_b64(helm: dict, b64_value: str) -> None:
    params = helm.setdefault("parameters", [])
    params.append(
        {
            "name": DISCOVERY_HELM_PARAM_B64,
            "value": b64_value,
            "forceString": True,
        }
    )


def _application_source_blob(src: dict) -> str:
    return (src.get("path") or "") + (src.get("chart") or "") + (src.get("repoURL") or "")


def upsert_netapp_discovery_json_on_application(
    app: dict, payload: Dict[str, Any], source_substring: str
) -> None:
    """Inject netappDrDiscoveryJsonB64 on the Helm source that actually renders this chart.

    Multisource hub Applications include a ref-only source; it may carry an empty `helm: {}`.
    Writing discovery parameters onto that source breaks Helm / Argo and can mark the app Degraded.
    """
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64_val = base64.b64encode(raw).decode("ascii")
    spec = app.setdefault("spec", {})
    sources = spec.get("sources")
    if sources:
        patched = 0
        for src in sources:
            helm = src.get("helm")
            if not isinstance(helm, dict):
                continue
            blob = _application_source_blob(src)
            if source_substring not in blob:
                continue
            _strip_discovery_helm_params(helm)
            _append_discovery_param_b64(helm, b64_val)
            patched += 1
        if patched == 0:
            # Fallback: first chart-like source (has path or chart), excluding ref-only rows.
            for src in sources:
                helm = src.get("helm")
                if not isinstance(helm, dict):
                    continue
                if not (src.get("path") or src.get("chart")):
                    continue
                print(
                    f"Warning: discovery param applied via fallback (no '{source_substring}' in source blob) "
                    f"on Application {(app.get('metadata') or {}).get('name')!r}",
                    file=sys.stderr,
                )
                _strip_discovery_helm_params(helm)
                _append_discovery_param_b64(helm, b64_val)
                patched += 1
                break
        if patched == 0:
            print(
                f"Warning: no Helm source patched for discovery on Application "
                f"{(app.get('metadata') or {}).get('name')!r} (substring {source_substring!r})",
                file=sys.stderr,
            )
        return
    src = spec.setdefault("source", {})
    blob = _application_source_blob(src)
    if source_substring not in blob:
        print(
            f"Warning: discovery substring {source_substring!r} not in single-source blob {blob!r} "
            f"for Application {(app.get('metadata') or {}).get('name')!r}",
            file=sys.stderr,
        )
    helm = src.setdefault("helm", {})
    if not isinstance(helm, dict):
        src["helm"] = {}
        helm = src["helm"]
    _strip_discovery_helm_params(helm)
    _append_discovery_param_b64(helm, b64_val)


def find_application_by_path_substring(namespace: str, substr: str) -> Optional[str]:
    raw = subprocess.run(
        ["oc", "get", "applications.argoproj.io", "-n", namespace, "-o", "json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    data = json.loads(raw)
    names: List[str] = []
    for item in data.get("items") or []:
        spec = item.get("spec") or {}
        candidates = []
        if spec.get("source"):
            candidates.append(spec["source"])
        for s in spec.get("sources") or []:
            candidates.append(s)
        for src in candidates:
            blob = _application_source_blob(src)
            if substr in blob:
                names.append(item["metadata"]["name"])
                break
    if not names:
        return None
    names.sort()
    return names[0]


def _remove_kubectl_last_applied_annotation(namespace: str, name: str) -> None:
    """Drop kubectl client annotation that Git/Helm does not render; it breaks Argo sync patches."""
    r = subprocess.run(
        [
            "oc",
            "annotate",
            "application.argoproj.io",
            name,
            "-n",
            namespace,
            "kubectl.kubernetes.io/last-applied-configuration-",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0 and "not found" not in (r.stderr or "").lower():
        print(
            f"Note: kubectl last-applied annotation strip on {namespace}/{name}: {r.stderr or r.stdout}",
            file=sys.stderr,
        )


def replace_argo_application(
    namespace: str, name: str, payload: Dict[str, Any], source_substring: str
) -> None:
    """Update only Helm parameters (discovery B64); avoid full oc replace on Application CRs.

    Full replace can confuse Argo CD sync (e.g. resourceVersion / patch apply errors on the hub).
    """
    raw = subprocess.run(
        ["oc", "get", "application.argoproj.io", name, "-n", namespace, "-o", "json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    app = json.loads(raw)
    upsert_netapp_discovery_json_on_application(app, payload, source_substring)
    spec = app.get("spec") or {}
    sources = spec.get("sources") or []
    patch_path = ""
    try:
        if sources:
            ops: List[Dict[str, Any]] = []
            for i, src in enumerate(sources):
                helm = src.get("helm")
                if not isinstance(helm, dict):
                    continue
                if source_substring not in _application_source_blob(src):
                    continue
                params = helm.get("parameters")
                if params is None:
                    continue
                ops.append({"op": "replace", "path": f"/spec/sources/{i}/helm/parameters", "value": params})
            if not ops:
                print(
                    f"Warning: no multisource helm.parameters patch ops for {namespace}/{name} "
                    f"(substring {source_substring!r})",
                    file=sys.stderr,
                )
                return
            body = json.dumps(ops)
            r = subprocess.run(
                [
                    "oc",
                    "patch",
                    "application.argoproj.io",
                    name,
                    "-n",
                    namespace,
                    "--type=json",
                    "-p",
                    body,
                ],
                capture_output=True,
                text=True,
            )
            if r.returncode != 0:
                print(
                    f"json patch parameters failed for {namespace}/{name}: {r.stderr or r.stdout}",
                    file=sys.stderr,
                )
                raise subprocess.CalledProcessError(r.returncode, r.args, output=r.stdout, stderr=r.stderr)
            _remove_kubectl_last_applied_annotation(namespace, name)
            return

        # Single-source Application (common for VP-rendered child apps).
        src = spec.get("source") or {}
        helm = src.get("helm")
        if not isinstance(helm, dict):
            helm = {}
        params = helm.get("parameters")
        if params is None:
            params = []
        merge_body = {"spec": {"source": {"helm": {"parameters": params}}}}
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(merge_body, f)
            patch_path = f.name
        r = subprocess.run(
            [
                "oc",
                "patch",
                "application.argoproj.io",
                name,
                "-n",
                namespace,
                "--type=merge",
                "--patch-file",
                patch_path,
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            print(
                f"merge patch parameters failed for {namespace}/{name}: {r.stderr or r.stdout}",
                file=sys.stderr,
            )
            raise subprocess.CalledProcessError(r.returncode, r.args, output=r.stdout, stderr=r.stderr)
        _remove_kubectl_last_applied_annotation(namespace, name)
    finally:
        if patch_path:
            try:
                os.unlink(patch_path)
            except OSError:
                pass


def refresh_argo_application(namespace: str, name: str) -> None:
    """Ask Argo CD to re-render Helm with updated parameters (e.g. after discovery B64 patch)."""
    if not namespace or not name:
        return
    r = subprocess.run(
        [
            "oc",
            "annotate",
            "application.argoproj.io",
            name,
            "-n",
            namespace,
            "argocd.argoproj.io/refresh=hard",
            "--overwrite",
        ],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        print(
            f"Warning: hard refresh on {namespace}/{name}: {r.stderr or r.stdout}",
            file=sys.stderr,
        )
    else:
        print(f"Hard refresh requested for Argo CD Application {namespace}/{name}")


def request_argo_sync(namespace: str, name: str, *, prune: bool = False) -> None:
    """Queue a sync on an Application (used after discovery injects helm parameters)."""
    if not namespace or not name:
        return
    patch = {
        "operation": {
            "initiatedBy": {"username": "crossplane-network-discovery"},
            "sync": {"prune": prune},
        }
    }
    patch_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(patch, f)
            patch_path = f.name
        r = subprocess.run(
            [
                "oc",
                "patch",
                "application.argoproj.io",
                name,
                "-n",
                namespace,
                "--type=merge",
                "--patch-file",
                patch_path,
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            print(
                f"Warning: sync request failed for {namespace}/{name}: {r.stderr or r.stdout}",
                file=sys.stderr,
            )
        else:
            print(f"Sync requested for Argo CD Application {namespace}/{name}")
    finally:
        if patch_path:
            try:
                os.unlink(patch_path)
            except OSError:
                pass


def count_ontap_filesystems() -> int:
    r = subprocess.run(
        ["oc", "get", "ontapfilesystems.fsx.aws.upbound.io", "-o", "json"],
        capture_output=True,
        text=True,
    )
    if r.returncode != 0:
        return 0
    data = json.loads(r.stdout or "{}")
    return len(data.get("items") or [])


def application_has_discovery_b64(namespace: str, name: str) -> bool:
    try:
        raw = subprocess.run(
            ["oc", "get", "application.argoproj.io", name, "-n", namespace, "-o", "json"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError:
        return False
    app = json.loads(raw)
    spec = app.get("spec") or {}
    sources = spec.get("sources") or []
    if not sources and spec.get("source"):
        sources = [spec["source"]]
    for src in sources:
        helm = src.get("helm") or {}
        for p in helm.get("parameters") or []:
            if p.get("name") == DISCOVERY_HELM_PARAM_B64 and (p.get("value") or "").strip():
                return True
    return False


def resolve_child_application(namespace: str, env_name: str, auto: bool, substring: str) -> str:
    name = os.environ.get(env_name, "").strip()
    if namespace and not name and auto:
        name = find_application_by_path_substring(namespace, substring) or ""
    return name


def adopt_security_group_external_names() -> None:
    """Annotate FSx security group CRs with crossplane.io/external-name so they adopt existing AWS SGs."""
    if os.environ.get("ADOPT_FSX_SECURITY_GROUPS", "true").lower() != "true":
        return
    kubeconfig = os.environ.get("KUBECONFIG", "").strip()
    oc = ["oc"]
    if kubeconfig:
        oc.extend(["--kubeconfig", kubeconfig])
    try:
        sg_list = json.loads(
            subprocess.run(
                [*oc, "get", "securitygroup.ec2.aws.upbound.io", "-o", "json"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
    except subprocess.CalledProcessError:
        return
    for item in sg_list.get("items") or []:
        meta = item.get("metadata") or {}
        name = meta.get("name") or ""
        if not name.endswith("-sg"):
            continue
        ann = meta.get("annotations") or {}
        if (ann.get("crossplane.io/external-name") or "").strip():
            continue
        region = ((item.get("spec") or {}).get("forProvider") or {}).get("region") or ""
        if not region:
            continue
        sg_aws_name = name
        try:
            out = subprocess.run(
                [
                    "aws",
                    "ec2",
                    "describe-security-groups",
                    "--region",
                    region,
                    "--filters",
                    f"Name=group-name,Values={sg_aws_name}",
                    "--query",
                    "SecurityGroups[0].GroupId",
                    "--output",
                    "text",
                ],
                capture_output=True,
                text=True,
            )
            if out.returncode != 0 or not (out.stdout or "").strip() or out.stdout.strip() == "None":
                continue
            ext_id = out.stdout.strip()
            print(f"Adopting SecurityGroup/{name} external-name={ext_id}")
            subprocess.run(
                [
                    *oc,
                    "annotate",
                    "securitygroup.ec2.aws.upbound.io",
                    name,
                    f"crossplane.io/external-name={ext_id}",
                    "--overwrite",
                ],
                capture_output=True,
                text=True,
            )
        except (subprocess.CalledProcessError, OSError):
            continue


def retry_vpc_peering_connection_options() -> None:
    """Delete options CRs that failed while peering was pending so Crossplane recreates them when active."""
    if os.environ.get("RETRY_VPC_PEERING_OPTIONS", "true").lower() != "true":
        return
    kubeconfig = os.environ.get("KUBECONFIG", "").strip()
    oc = ["oc"]
    if kubeconfig:
        oc.extend(["--kubeconfig", kubeconfig])
    try:
        peerings = json.loads(
            subprocess.run(
                [*oc, "get", "vpcpeeringconnection.ec2.aws.upbound.io", "-o", "json"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
    except subprocess.CalledProcessError:
        return
    active = any(
        (
            ((item.get("status") or {}).get("atProvider") or {}).get("acceptStatus") or ""
        ).lower()
        == "active"
        for item in peerings.get("items") or []
    )
    if not active:
        return
    try:
        opts_list = json.loads(
            subprocess.run(
                [*oc, "get", "vpcpeeringconnectionoptions.ec2.aws.upbound.io", "-o", "json"],
                capture_output=True,
                text=True,
                check=True,
            ).stdout
        )
    except subprocess.CalledProcessError:
        return
    for item in opts_list.get("items") or []:
        name = (item.get("metadata") or {}).get("name") or ""
        if not name:
            continue
        conds = (item.get("status") or {}).get("conditions") or []
        last_async = next((c for c in conds if c.get("type") == "LastAsyncOperation"), {})
        at = (item.get("status") or {}).get("atProvider") or {}
        req = at.get("requester") or {}
        acc = at.get("accepter") or {}
        spec_fp = (item.get("spec") or {}).get("forProvider") or {}
        wants_dns = bool((spec_fp.get("requester") or {}).get("allowRemoteVpcDnsResolution")) or bool(
            (spec_fp.get("accepter") or {}).get("allowRemoteVpcDnsResolution")
        )
        has_dns = bool(req.get("allowRemoteVpcDnsResolution")) or bool(acc.get("allowRemoteVpcDnsResolution"))
        if last_async.get("status") == "False" or (wants_dns and not has_dns):
            print(f"Deleting VPCPeeringConnectionOptions/{name} for retry (peering active)")
            subprocess.run(
                [*oc, "delete", "vpcpeeringconnectionoptions.ec2.aws.upbound.io", name, "--wait=false"],
                capture_output=True,
                text=True,
            )


def post_discovery_resync() -> None:
    """After patching discovery B64, trigger refresh + follow-up sync so Helm renders both FSx filesystems."""
    if os.environ.get("TRIGGER_ARGO_RESYNC", "true").lower() != "true":
        return
    argo_ns = os.environ.get("ARGOCD_APPLICATION_NAMESPACE", "").strip()
    if not argo_ns and os.environ.get("GLOBAL_PATTERN", "").strip():
        argo_ns = f"{os.environ.get('GLOBAL_PATTERN', '').strip()}-hub"
    patch_cp = os.environ.get("PATCH_ARGOCD_CROSSPLANE_APP", "false").lower() == "true"
    patch_dr = os.environ.get("PATCH_ARGOCD_DR_DNS_APP", "false").lower() == "true"
    cp_auto = os.environ.get("PATCH_ARGOCD_AUTO", "false").lower() == "true"
    dr_auto = os.environ.get("PATCH_ARGOCD_DR_DNS_AUTO", "false").lower() == "true"
    cp_name = resolve_child_application(argo_ns, "ARGOCD_APPLICATION_NAME", cp_auto, "crossplane-aws-infra")
    dr_ns = os.environ.get("ARGOCD_DR_DNS_APPLICATION_NAMESPACE", "").strip() or argo_ns
    dr_name = resolve_child_application(dr_ns, "ARGOCD_DR_DNS_APPLICATION_NAME", dr_auto, "dr-dns-reconciler")

    targets: List[tuple[str, str]] = []
    if patch_cp and cp_name:
        targets.append((argo_ns, cp_name))
    if patch_dr and dr_name:
        targets.append((dr_ns, dr_name))
    for ns, name in targets:
        refresh_argo_application(ns, name)
        request_argo_sync(ns, name, prune=False)


def postsync_hook_main() -> int:
    """PostSync: if discovery B64 is set but fewer than two FSx CRs exist, queue another sync."""
    role = os.environ.get("PATTERN_CLUSTER_ROLE", "hub").strip()
    if role != "hub":
        return 0
    argo_ns = os.environ.get("ARGOCD_APPLICATION_NAMESPACE", "").strip()
    if not argo_ns and os.environ.get("GLOBAL_PATTERN", "").strip():
        argo_ns = f"{os.environ.get('GLOBAL_PATTERN', '').strip()}-hub"
    cp_name = resolve_child_application(
        argo_ns,
        "ARGOCD_APPLICATION_NAME",
        os.environ.get("PATCH_ARGOCD_AUTO", "true").lower() == "true",
        "crossplane-aws-infra",
    )
    if not argo_ns or not cp_name:
        print("PostSync: skip (no crossplane-aws-infra Application namespace/name)")
        return 0
    fsx_count = count_ontap_filesystems()
    print(f"PostSync: OntapFileSystem count={fsx_count}")
    if fsx_count >= 2:
        return 0
    if not application_has_discovery_b64(argo_ns, cp_name):
        print("PostSync: discovery B64 not on Application yet; skipping resync")
        return 0
    print("PostSync: discovery present but FSx CRs < 2; requesting another sync")
    refresh_argo_application(argo_ns, cp_name)
    request_argo_sync(argo_ns, cp_name, prune=False)
    return 0


def patch_argo_applications_for_hub(payload: Dict[str, Any]) -> None:
    patch_cp = os.environ.get("PATCH_ARGOCD_CROSSPLANE_APP", "false").lower() == "true"
    patch_dr = os.environ.get("PATCH_ARGOCD_DR_DNS_APP", "false").lower() == "true"
    if not patch_cp and not patch_dr:
        return
    argo_ns = os.environ.get("ARGOCD_APPLICATION_NAMESPACE", "").strip()
    argo_name = os.environ.get("ARGOCD_APPLICATION_NAME", "").strip()
    auto = os.environ.get("PATCH_ARGOCD_AUTO", "false").lower() == "true"
    if patch_cp and argo_ns and not argo_name and auto:
        argo_name = find_application_by_path_substring(argo_ns, "crossplane-aws-infra") or ""
    dr_ns = os.environ.get("ARGOCD_DR_DNS_APPLICATION_NAMESPACE", "").strip() or argo_ns
    dr_name = os.environ.get("ARGOCD_DR_DNS_APPLICATION_NAME", "").strip()
    dr_auto = os.environ.get("PATCH_ARGOCD_DR_DNS_AUTO", "false").lower() == "true"
    if patch_dr and dr_ns and not dr_name and dr_auto:
        dr_name = find_application_by_path_substring(dr_ns, "dr-dns-reconciler") or ""

    done: set[tuple[str, str]] = set()

    def do_patch(ns: str, name: str, source_substring: str) -> None:
        if not ns or not name or (ns, name) in done:
            return
        print(f"Patching Argo CD Application {ns}/{name} ({DISCOVERY_HELM_PARAM_B64})")
        replace_argo_application(ns, name, payload, source_substring)
        done.add((ns, name))

    if patch_cp:
        do_patch(argo_ns, argo_name, "crossplane-aws-infra")
    if patch_dr:
        do_patch(dr_ns, dr_name, "dr-dns-reconciler")


def _ignore_entry_key(entry: Dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(entry.get("group") or ""),
        str(entry.get("kind") or ""),
        str(entry.get("name") or ""),
        str(entry.get("namespace") or ""),
    )


def _merge_discovery_parent_ignore_differences(app: dict) -> bool:
    """Merge ignoreDifferences rules onto the hub Pattern (app-of-apps) Application."""
    spec = app.setdefault("spec", {})
    raw_existing: List[Any] = list(spec.get("ignoreDifferences") or [])
    wants = _discovery_parent_ignore_entries()
    if not wants:
        return False

    out: List[Any] = []
    # Drop legacy unscoped rule from earlier chart versions (jq select on parameters).
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
        # Replace any prior discovery-managed child rule (name match; any namespace / jq / json mix).
        if (
            entry.get("group") == "argoproj.io"
            and entry.get("kind") == "Application"
            and (entry.get("name") or "") in DISCOVERY_MANAGED_CHILD_APP_NAMES
        ):
            continue
        out.append(entry)

    changed = bool(len(out) != len(raw_existing))
    for want in wants:
        key = _ignore_entry_key(want)
        idx: Optional[int] = None
        for i, e in enumerate(out):
            if isinstance(e, dict) and _ignore_entry_key(e) == key:
                idx = i
                break
        want_ptrs = [str(x) for x in (want.get("jsonPointers") or [])]
        want_jqs = [str(x) for x in (want.get("jqPathExpressions") or [])]
        if idx is None:
            out.append(dict(want))
            changed = True
            continue
        cur = dict(out[idx])
        entry_changed = False
        if cur.get("namespace"):
            del cur["namespace"]
            entry_changed = True
        if cur.get("jqPathExpressions"):
            legacy = any("netappDrDiscoveryJson" in str(j) for j in (cur.get("jqPathExpressions") or []))
            if legacy:
                del cur["jqPathExpressions"]
                entry_changed = True
        cur_ptrs = [str(x) for x in (cur.get("jsonPointers") or [])]
        merged = list(cur_ptrs)
        for p in want_ptrs:
            if p not in merged:
                merged.append(p)
        merged_norm = _stable_sorted_unique_pointers(merged)
        cur_norm = _stable_sorted_unique_pointers(cur_ptrs)
        if merged_norm != cur_norm:
            cur["jsonPointers"] = merged_norm
            entry_changed = True
        if want_jqs:
            cur_jqs = [str(x) for x in (cur.get("jqPathExpressions") or [])]
            if sorted(cur_jqs) != sorted(want_jqs):
                cur["jqPathExpressions"] = list(want_jqs)
                entry_changed = True
        if entry_changed:
            out[idx] = cur
            changed = True

    if not changed:
        return False
    spec["ignoreDifferences"] = out
    return True


_RESPECT_IGNORE_DIFFERENCES_SYNC_OPTION = "RespectIgnoreDifferences=true"


def _ensure_parent_respect_ignore_differences(app: dict) -> bool:
    """Ensure hub Application syncPolicy includes RespectIgnoreDifferences (operator may strip it)."""
    spec = app.setdefault("spec", {})
    sp = spec.setdefault("syncPolicy", {})
    opts = list(sp.get("syncOptions") or [])
    if _RESPECT_IGNORE_DIFFERENCES_SYNC_OPTION in opts:
        return False
    opts.append(_RESPECT_IGNORE_DIFFERENCES_SYNC_OPTION)
    sp["syncOptions"] = opts
    return True


def patch_parent_pattern_application_ignore_differences() -> None:
    if os.environ.get("PATCH_ARGOCD_PARENT_IGNORE_DIFFERENCES", "false").lower() != "true":
        return
    ns = os.environ.get("ARGOCD_PARENT_APPLICATION_NAMESPACE", "").strip() or "vp-gitops"
    name = os.environ.get("ARGOCD_PARENT_APPLICATION_NAME", "").strip()
    if not name:
        pattern = os.environ.get("GLOBAL_PATTERN", "").strip()
        cg = os.environ.get("CLUSTER_GROUP_NAME", "").strip()
        if pattern and cg:
            name = f"{pattern}-{cg}"
    if not name:
        print(
            "Skipping parent Application ignoreDifferences patch: set ARGOCD_PARENT_APPLICATION_NAME or GLOBAL_PATTERN+CLUSTER_GROUP_NAME",
            file=sys.stderr,
        )
        return
    try:
        raw = subprocess.run(
            ["oc", "get", "application.argoproj.io", name, "-n", ns, "-o", "json"],
            capture_output=True,
            text=True,
            check=True,
        ).stdout
    except subprocess.CalledProcessError as e:
        print(
            f"Skipping parent ignoreDifferences patch ({ns}/{name}): {e.stderr or e}",
            file=sys.stderr,
        )
        return
    app = json.loads(raw)
    idiff_changed = _merge_discovery_parent_ignore_differences(app)
    syncopt_changed = _ensure_parent_respect_ignore_differences(app)
    if not idiff_changed and not syncopt_changed:
        return
    patch_spec: Dict[str, Any] = {}
    if idiff_changed:
        patch_spec["ignoreDifferences"] = app["spec"]["ignoreDifferences"]
    if syncopt_changed:
        patch_spec["syncPolicy"] = {"syncOptions": app["spec"]["syncPolicy"]["syncOptions"]}
    patch_body = {"spec": patch_spec}
    parts = []
    if idiff_changed:
        parts.append(
            "ignoreDifferences (child Applications "
            f"{', '.join(sorted(DISCOVERY_MANAGED_CHILD_APP_NAMES))})"
        )
    if syncopt_changed:
        parts.append(f"syncPolicy.syncOptions ({_RESPECT_IGNORE_DIFFERENCES_SYNC_OPTION})")
    print(f"Patching Argo CD Application {ns}/{name}: " + "; ".join(parts))
    patch_path = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(patch_body, f)
            patch_path = f.name
        r = subprocess.run(
            [
                "oc",
                "patch",
                "application.argoproj.io",
                name,
                "-n",
                ns,
                "--type=merge",
                "--patch-file",
                patch_path,
            ],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            print(
                f"merge patch ignoreDifferences failed ({r.stderr or r.stdout}); falling back to oc replace: {r}",
                file=sys.stderr,
            )
            _strip_application_for_server_replace(app)
            rep_path = ""
            try:
                with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as rf:
                    json.dump(app, rf)
                    rep_path = rf.name
                subprocess.run(["oc", "replace", "-f", rep_path], check=True)
            finally:
                if rep_path:
                    try:
                        os.unlink(rep_path)
                    except OSError:
                        pass
    finally:
        if patch_path:
            try:
                os.unlink(patch_path)
            except OSError:
                pass


def main() -> int:
    role = os.environ.get("PATTERN_CLUSTER_ROLE", "hub").strip()
    remote_kc = os.environ.get("REMOTE_KUBECONFIG_PATH", "").strip()
    ns = os.environ.get("DISCOVERY_CONFIGMAP_NAMESPACE", "crossplane-system").strip()
    cm_name = os.environ.get("DISCOVERY_CONFIGMAP_NAME", "crossplane-network-discovery").strip()
    appvault_bucket = os.environ.get("APPVAULT_BUCKET", "").strip()
    appvault_region = os.environ.get("APPVAULT_REGION", "").strip()
    dr_domain_git = os.environ.get("DR_FAILOVER_DOMAIN", "").strip()
    discover_hosted_zone = os.environ.get("ROUTE53_DISCOVER_HOSTED_ZONE", "true").lower() == "true"
    discover_parent = os.environ.get("ROUTE53_DISCOVER_HOSTED_ZONE_PARENT", "true").lower() == "true"
    zone_lookup_override = os.environ.get("ROUTE53_ZONE_LOOKUP_NAME", "").strip()
    explicit_zone = os.environ.get("ROUTE53_HOSTED_ZONE_ID_EXPLICIT", "").strip()
    create_hosted_zone_git = os.environ.get("ROUTE53_CREATE_HOSTED_ZONE", "true").lower() == "true"

    if role == "secondary":
        if not remote_kc or not os.path.isfile(remote_kc):
            print("REMOTE_KUBECONFIG_PATH must be set to the primary cluster kubeconfig file", file=sys.stderr)
            return 1
        local = discover_cluster(None, "local(secondary)")
        remote = discover_cluster(remote_kc, "remote(primary)")
        out: Dict[str, Any] = {
            "endpointWatcher": {
                "local": {
                    "fileSystemName": fsx_name(local["cluster_name"], local["region"]),
                    "region": local["region"],
                    "svmName": "SVM2",
                },
                "peer": {
                    "fileSystemName": fsx_name(remote["cluster_name"], remote["region"]),
                    "region": remote["region"],
                    "svmName": "SVM1",
                },
            },
            "global": {
                "localClusterDomain": remote["ingress_domain"],
                "drClusterDomain": local["ingress_domain"],
                "clusterDomain": remote["ingress_domain"],
            },
            "_discoveryComplete": True,
        }
        apply_configmap(ns, cm_name, {"discovery.json": json.dumps(out, indent=2)})
        print("secondary discovery written")
        return 0

    # hub — parent ignore first so app-of-apps sync does not revert discovery helm parameters.
    patch_parent_pattern_application_ignore_differences()

    if not remote_kc or not os.path.isfile(remote_kc):
        print("REMOTE_KUBECONFIG_PATH must be set to the DR cluster kubeconfig file", file=sys.stderr)
        return 1
    if not appvault_bucket:
        print("APPVAULT_BUCKET must be set (tridentProtect.appVault.s3.bucketName in values-global)", file=sys.stderr)
        return 1
    prod = discover_cluster(None, "local(hub/prod)")
    dr = discover_cluster(remote_kc, "remote(dr)")

    if dr_domain_git:
        failover_domain = dr_domain_git
    else:
        parts = prod["base_domain"].split(".", 1)
        failover_domain = "dr." + parts[1] if len(parts) > 1 else f"dr.{prod['base_domain']}"

    zone_id = explicit_zone
    if not zone_id and discover_hosted_zone:
        lookup_name = zone_lookup_override or failover_domain
        zone_id = route53_lookup_zone_id(lookup_name, prod["region"])
        if not zone_id and discover_parent and failover_domain.startswith("dr."):
            parent = failover_domain[3:]
            if parent:
                zone_id = route53_lookup_zone_id(parent, prod["region"])

    create_hosted_zone = create_hosted_zone_git and not bool(zone_id)
    if not zone_id:
        zone_id = crossplane_zone_id(failover_domain)

    route53_out: Dict[str, Any] = {
        "domain": failover_domain,
        "createHostedZone": create_hosted_zone,
        "region": prod["region"],
    }
    if zone_id:
        route53_out["hostedZoneId"] = zone_id
    drdns_out: Dict[str, Any] = {
        "domain": failover_domain,
        "s3Bucket": appvault_bucket,
        "s3Region": appvault_region or prod["region"],
    }
    if zone_id:
        drdns_out["hostedZoneId"] = zone_id

    out = {
        "global": {
            "localClusterDomain": prod["ingress_domain"],
            "drClusterDomain": dr["ingress_domain"],
            "clusterDomain": prod["ingress_domain"],
        },
        "fsxOntap": {
            "enabled": True,
            "region": prod["region"],
            "fileSystemName": fsx_name(prod["cluster_name"], prod["region"]),
            "svmName": "SVM1",
            "vpcId": prod["vpc_id"],
            "subnetIds": prod["subnet_ids"][:2],
            "routeTableIds": prod["route_table_ids"],
            "preferredSubnetId": prod["subnet_ids"][0],
            "allowedCidrs": [prod["vpc_cidr"], dr["vpc_cidr"]],
            "peer": {
                "enabled": True,
                "region": dr["region"],
                "fileSystemName": fsx_name(dr["cluster_name"], dr["region"]),
                "vpcId": dr["vpc_id"],
                "subnetIds": dr["subnet_ids"][:2],
                "routeTableIds": dr["route_table_ids"],
                "preferredSubnetId": dr["subnet_ids"][0],
                "allowedCidrs": [dr["vpc_cidr"], prod["vpc_cidr"]],
                "svmName": "SVM2",
            },
        },
        "s3AppVault": {
            "bucketName": appvault_bucket,
            "region": appvault_region or prod["region"],
        },
        "endpointWatcher": {
            "local": {
                "fileSystemName": fsx_name(prod["cluster_name"], prod["region"]),
                "region": prod["region"],
                "svmName": "SVM1",
            },
            "peer": {
                "fileSystemName": fsx_name(dr["cluster_name"], dr["region"]),
                "region": dr["region"],
                "svmName": "SVM2",
            },
        },
        "vpcPeering": {
            "enabled": True,
            "prod": {
                "region": prod["region"],
                "vpcId": prod["vpc_id"],
                "vpcCidr": prod["vpc_cidr"],
                "clusterName": prod["cluster_name"],
                "routeTableIds": prod["all_route_table_ids"],
            },
            "dr": {
                "region": dr["region"],
                "vpcId": dr["vpc_id"],
                "vpcCidr": dr["vpc_cidr"],
                "clusterName": dr["cluster_name"],
                "routeTableIds": dr["all_route_table_ids"],
            },
        },
        "route53Failover": route53_out,
        "drDnsReconciler": drdns_out,
        "_discoveryComplete": True,
    }
    apply_configmap(ns, cm_name, {"discovery.json": json.dumps(out, indent=2)})
    print("hub discovery written")
    patch_argo_applications_for_hub(out)
    adopt_security_group_external_names()
    retry_vpc_peering_connection_options()
    post_discovery_resync()
    return 0


def parent_ignore_guard_main() -> int:
    """Re-apply hub Pattern Application ignoreDifferences (wiped by parent selfHeal from Git)."""
    patch_parent_pattern_application_ignore_differences()
    return 0


if __name__ == "__main__":
    try:
        if os.environ.get("ARGOCD_PARENT_IGNORE_GUARD", "").lower() == "true":
            raise SystemExit(parent_ignore_guard_main())
        hook = os.environ.get("DISCOVERY_HOOK", "").strip().lower()
        if hook == "postsync":
            raise SystemExit(postsync_hook_main())
        raise SystemExit(main())
    except Exception as e:  # noqa: BLE001
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
