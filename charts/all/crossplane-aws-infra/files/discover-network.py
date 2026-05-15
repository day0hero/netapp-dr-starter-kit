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
# helm.parameters on the specific child Applications discovery mutates.
#
# We scope by metadata.name + namespace (Argo diff customization) and ignore whole
# .spec.source.helm.parameters / per-source helm.parameters — fine-grained jq|select()
# is unreliable across Argo CD versions for app-of-apps (see argoproj/argo-cd#19680).
def _discovery_parent_ignore_entries(child_ns: str) -> List[Dict[str, Any]]:
    if not child_ns:
        return []
    out: List[Dict[str, Any]] = []
    for app_name in ("crossplane-aws-infra", "dr-dns-reconciler"):
        out.append(
            {
                "group": "argoproj.io",
                "kind": "Application",
                "name": app_name,
                "namespace": child_ns,
                "jqPathExpressions": [
                    ".spec.source.helm.parameters",
                    '.spec.sources[] | select(.helm != null) | .helm.parameters',
                ],
            }
        )
    return out


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


def upsert_netapp_discovery_json_on_application(app: dict, payload: Dict[str, Any]) -> None:
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    b64_val = base64.b64encode(raw).decode("ascii")
    spec = app.setdefault("spec", {})
    sources = spec.get("sources")
    if sources:
        for src in sources:
            helm = src.get("helm")
            if helm is not None:
                _strip_discovery_helm_params(helm)
                _append_discovery_param_b64(helm, b64_val)
        return
    src = spec.setdefault("source", {})
    helm = src.setdefault("helm", {})
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
            blob = (src.get("path") or "") + (src.get("chart") or "") + (src.get("repoURL") or "")
            if substr in blob:
                names.append(item["metadata"]["name"])
                break
    if not names:
        return None
    names.sort()
    return names[0]


def replace_argo_application(namespace: str, name: str, payload: Dict[str, Any]) -> None:
    raw = subprocess.run(
        ["oc", "get", "application.argoproj.io", name, "-n", namespace, "-o", "json"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    app = json.loads(raw)
    upsert_netapp_discovery_json_on_application(app, payload)
    path = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(app, f)
            path = f.name
        subprocess.run(["oc", "replace", "-f", path], check=True)
    finally:
        if path:
            try:
                os.unlink(path)
            except OSError:
                pass


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

    def do_patch(ns: str, name: str) -> None:
        if not ns or not name or (ns, name) in done:
            return
        print(f"Patching Argo CD Application {ns}/{name} ({DISCOVERY_HELM_PARAM_B64})")
        replace_argo_application(ns, name, payload)
        done.add((ns, name))

    if patch_cp:
        do_patch(argo_ns, argo_name)
    if patch_dr:
        do_patch(dr_ns, dr_name)


def _ignore_entry_key(entry: Dict[str, Any]) -> tuple[str, str, str, str]:
    return (
        str(entry.get("group") or ""),
        str(entry.get("kind") or ""),
        str(entry.get("name") or ""),
        str(entry.get("namespace") or ""),
    )


def _merge_discovery_parent_ignore_differences(app: dict, child_ns: str) -> bool:
    """Merge scoped ignoreDifferences rules onto the hub Pattern (app-of-apps) Application."""
    spec = app.setdefault("spec", {})
    raw_existing: List[Any] = list(spec.get("ignoreDifferences") or [])
    wants = _discovery_parent_ignore_entries(child_ns)
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
        out.append(entry)

    changed = bool(len(out) != len(raw_existing))
    for want in wants:
        key = _ignore_entry_key(want)
        want_jq = [str(x) for x in (want.get("jqPathExpressions") or [])]
        idx: Optional[int] = None
        for i, e in enumerate(out):
            if isinstance(e, dict) and _ignore_entry_key(e) == key:
                idx = i
                break
        if idx is None:
            out.append(dict(want))
            changed = True
            continue
        cur = out[idx]
        cur_jq = [str(x) for x in (cur.get("jqPathExpressions") or [])]
        merged = list(cur_jq)
        for expr in want_jq:
            if expr not in merged:
                merged.append(expr)
        if merged != cur_jq:
            cur = dict(cur)
            cur["jqPathExpressions"] = merged
            out[idx] = cur
            changed = True

    if not changed:
        return False
    spec["ignoreDifferences"] = out
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
    child_ns = os.environ.get("ARGOCD_CHILD_APPLICATION_NAMESPACE", "").strip()
    if not child_ns:
        child_ns = os.environ.get("ARGOCD_APPLICATION_NAMESPACE", "").strip()
    if not child_ns:
        print(
            "Skipping parent ignoreDifferences patch: ARGOCD_APPLICATION_NAMESPACE is empty",
            file=sys.stderr,
        )
        return
    if not _merge_discovery_parent_ignore_differences(app, child_ns):
        return
    print(f"Patching Argo CD Application {ns}/{name} (ignoreDifferences for discovery helm parameters on child Applications)")
    path = ""
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(app, f)
            path = f.name
        subprocess.run(["oc", "replace", "-f", path], check=True)
    finally:
        if path:
            try:
                os.unlink(path)
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

    # hub
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
    patch_parent_pattern_application_ignore_differences()
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as e:  # noqa: BLE001
        print(str(e), file=sys.stderr)
        raise SystemExit(1)
