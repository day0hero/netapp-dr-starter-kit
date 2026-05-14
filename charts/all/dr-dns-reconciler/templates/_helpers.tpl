{{/*
OpenShift default router: explicit drDnsReconciler *IngressHostname, else router-default.<ingressDomain>.
ingressDomain is global.clusterDomain (primary) / global.drClusterDomain (DR).
*/}}
{{- define "dr-dns-reconciler.routerHostname" -}}
{{- if .explicit -}}
{{- .explicit -}}
{{- else if .domain -}}
router-default.{{ .domain }}
{{- end -}}
{{- end }}

{{- define "dr-dns-reconciler.labels" -}}
app.kubernetes.io/name: dr-dns-reconciler
app.kubernetes.io/managed-by: {{ .Release.Service }}
{{- end }}

{{/*
Per-app names for Route53 (wordpress.dr.<domain>, …). Prefer drDnsReconciler.apps;
if empty, derive from drFailover.apps so DR routes and DNS stay aligned with one list.
*/}}
{{- define "dr-dns-reconciler.appsJson" -}}
{{- $c := .Values.drDnsReconciler }}
{{- if and $c.apps (gt (len $c.apps) 0) }}
{{- $c.apps | toJson -}}
{{- else }}
{{- $df := .Values.drFailover | default dict }}
{{- if and ($df.apps | default list) (gt (len $df.apps) 0) }}
{{- $list := list }}
{{- range $df.apps }}
{{- $list = append $list (dict "name" .name) }}
{{- end }}
{{- $list | toJson -}}
{{- else }}
{{- "[]" -}}
{{- end }}
{{- end }}
{{- end }}

{{- define "dr-dns-reconciler.discoveryDict" -}}
{{- $nd := .Values.networkDiscovery | default dict }}
{{- $ns := $nd.configMapNamespace | default "crossplane-system" }}
{{- $name := $nd.configMapName | default "crossplane-network-discovery" }}
{{- $cm := lookup "v1" "ConfigMap" $ns $name }}
{{- if and $cm $cm.data (index $cm.data "discovery.json") }}
{{- index $cm.data "discovery.json" | fromJson | toJson }}
{{- else }}
{{- dict | toJson }}
{{- end }}
{{- end }}

{{- define "dr-dns-reconciler.mergedDrDns" -}}
{{- $disc := include "dr-dns-reconciler.discoveryDict" . | fromJson }}
{{- mergeOverwrite (deepCopy .Values.drDnsReconciler) ($disc.drDnsReconciler | default dict) | toJson }}
{{- end }}

{{- define "dr-dns-reconciler.mergedGlobal" -}}
{{- $disc := include "dr-dns-reconciler.discoveryDict" . | fromJson }}
{{- mergeOverwrite (deepCopy (.Values.global | default dict)) ($disc.global | default dict) | toJson }}
{{- end }}

{{- define "dr-dns-reconciler.discoveryRenderable" -}}
{{- $c := include "dr-dns-reconciler.mergedDrDns" . | fromJson }}
{{- $g := include "dr-dns-reconciler.mergedGlobal" . | fromJson }}
{{- $primaryDomain := (coalesce $g.localClusterDomain $g.clusterDomain) }}
{{- $secondaryDomain := (coalesce $g.drClusterDomain $g.hubClusterDomain) }}
{{- $primaryIngress := include "dr-dns-reconciler.routerHostname" (dict "explicit" $c.primaryIngressHostname "domain" $primaryDomain) | trim }}
{{- $secondaryIngress := include "dr-dns-reconciler.routerHostname" (dict "explicit" $c.secondaryIngressHostname "domain" $secondaryDomain) | trim }}
{{- if and (ne ($c.hostedZoneId | default "") "") (ne ($c.domain | default "") "") (ne ($c.s3Bucket | default "") "") (ne ($c.s3Region | default "") "") (ne $primaryIngress "") (ne $secondaryIngress "") }}true{{- end }}
{{- end }}
