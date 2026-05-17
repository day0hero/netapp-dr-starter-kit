{{/*
OpenShift default router hostname: explicit override, else router-default.<ingressDomain>.
ingressDomain is global.clusterDomain / global.drClusterDomain (ingress.config/cluster spec.domain).
*/}}
{{- define "crossplane-aws-infra.routerHostname" -}}
{{- if .explicit -}}
{{- .explicit -}}
{{- else if .domain -}}
router-default.{{ .domain }}
{{- end -}}
{{- end }}

{{/*
Common labels for all Crossplane managed resources
*/}}
{{- define "crossplane-aws-infra.labels" -}}
app.kubernetes.io/managed-by: crossplane
app.kubernetes.io/part-of: netapp-dr-starter-kit
{{- end }}

{{/*
Provider config reference
*/}}
{{- define "crossplane-aws-infra.providerConfigRef" -}}
providerConfigRef:
  name: {{ .Values.global.providerConfigRef }}
{{- end }}

{{/*
Terraform aws_route53_record import ID / Crossplane external-name (hashicorp/aws createRecordImportID).
Required to adopt failover CNAME sets that already exist in Route53 (avoids InvalidChangeBatch "already exists").
*/}}
{{- define "crossplane-aws-infra.route53RecordExternalName" -}}
{{- printf "%s_%s_CNAME_%s" .zoneId (lower .recordName) .setIdentifier }}
{{- end }}

{{/*
Discovery merge data (same shape as discovery.json written by crossplane-network-discovery).

Argo CD does not evaluate Helm lookup() against the destination cluster, so ConfigMap-based
lookup is unreliable in GitOps. Prefer netappDrDiscoveryJson (local/file values) or
netappDrDiscoveryJsonB64 (Argo helm.parameters — raw JSON breaks Helm --set parsing on commas).

Priority: netappDrDiscoveryJson > netappDrDiscoveryJsonB64 > ConfigMap lookup (local helm) > empty.
*/}}
{{- define "crossplane-aws-infra.discoveryDict" -}}
{{- $inline := .Values.netappDrDiscoveryJson | default "" | trim }}
{{- if $inline }}
{{- $inline | fromJson | toJson }}
{{- else }}
{{- $b64 := .Values.netappDrDiscoveryJsonB64 | default "" | trim }}
{{- if $b64 }}
{{- $b64 | b64dec | fromJson | toJson }}
{{- else }}
{{- $cb := .Values.crossplaneBootstrap | default dict }}
{{- $ns := $cb.discoveryNamespace | default .Release.Namespace }}
{{- $name := $cb.discoveryConfigMapName | default "crossplane-network-discovery" }}
{{- $cm := lookup "v1" "ConfigMap" $ns $name }}
{{- if and $cm $cm.data (index $cm.data "discovery.json") }}
{{- index $cm.data "discovery.json" | fromJson | toJson }}
{{- else }}
{{- dict | toJson }}
{{- end }}
{{- end }}
{{- end }}
{{- end }}

{{- define "crossplane-aws-infra.mergedGlobal" -}}
{{- $disc := include "crossplane-aws-infra.discoveryDict" . | fromJson }}
{{- mergeOverwrite (deepCopy (.Values.global | default dict)) ($disc.global | default dict) | toJson }}
{{- end }}

{{- define "crossplane-aws-infra.mergedFsxOntap" -}}
{{- $disc := include "crossplane-aws-infra.discoveryDict" . | fromJson }}
{{- mergeOverwrite (deepCopy .Values.fsxOntap) ($disc.fsxOntap | default dict) | toJson }}
{{- end }}

{{- define "crossplane-aws-infra.mergedEndpointWatcher" -}}
{{- $disc := include "crossplane-aws-infra.discoveryDict" . | fromJson }}
{{- mergeOverwrite (deepCopy .Values.endpointWatcher) ($disc.endpointWatcher | default dict) | toJson }}
{{- end }}

{{- define "crossplane-aws-infra.mergedVpcPeering" -}}
{{- $disc := include "crossplane-aws-infra.discoveryDict" . | fromJson }}
{{- mergeOverwrite (deepCopy .Values.vpcPeering) ($disc.vpcPeering | default dict) | toJson }}
{{- end }}

{{- define "crossplane-aws-infra.mergedRoute53Failover" -}}
{{- $disc := include "crossplane-aws-infra.discoveryDict" . | fromJson }}
{{- mergeOverwrite (deepCopy .Values.route53Failover) ($disc.route53Failover | default dict) | toJson }}
{{- end }}

{{- define "crossplane-aws-infra.mergedS3AppVault" -}}
{{- $disc := include "crossplane-aws-infra.discoveryDict" . | fromJson }}
{{- $fromDisc := $disc.s3AppVault | default dict }}
{{- $tp := .Values.tridentProtect | default dict }}
{{- $av := ($tp.appVault).s3 | default dict }}
{{- $m := mergeOverwrite (deepCopy .Values.s3AppVault) $fromDisc }}
{{- /* Prefer values-global tridentProtect.appVault.s3 over chart default (trident-protect-bucket). */}}
{{- if $av.bucketName }}
{{- $_ := set $m "bucketName" $av.bucketName }}
{{- end }}
{{- if $av.region }}
{{- $_ := set $m "region" $av.region }}
{{- end }}
{{- $m | toJson }}
{{- end }}

{{- define "crossplane-aws-infra.vpcPeeringRenderable" -}}
{{- $vp := include "crossplane-aws-infra.mergedVpcPeering" . | fromJson }}
{{- if and ($vp.enabled | default false) (ne ($vp.prod.vpcId | default "") "") (ne ($vp.dr.vpcId | default "") "") }}true{{- end }}
{{- end }}

{{- define "crossplane-aws-infra.route53Renderable" -}}
{{- $r53 := include "crossplane-aws-infra.mergedRoute53Failover" . | fromJson }}
{{- $domainOk := ne ($r53.domain | default "") "" }}
{{- $zoneOk := or ($r53.createHostedZone | default false) (ne ($r53.hostedZoneId | default "") "") }}
{{- if and ($r53.enabled | default false) $domainOk $zoneOk }}true{{- end }}
{{- end }}

{{- define "crossplane-aws-infra.endpointWatcherRenderable" -}}
{{- $w := include "crossplane-aws-infra.mergedEndpointWatcher" . | fromJson }}
{{- if and (ne ($w.local.fileSystemName | default "") "") (ne ($w.local.region | default "") "") (ne ($w.peer.fileSystemName | default "") "") (ne ($w.peer.region | default "") "") }}true{{- end }}
{{- end }}

{{/*
True when Helm has discovery data (B64/inline param or completed ConfigMap merge).
First Argo sync without netappDrDiscoveryJsonB64 renders no FSx/VPC/Route53 claims; the Sync hook
discovery Job (wave 1, after wave-0 RBAC) patches the Application; PostSync triggers a second sync.
*/}}
{{- define "crossplane-aws-infra.discoveryProvisionable" -}}
{{- $b64 := .Values.netappDrDiscoveryJsonB64 | default "" | trim }}
{{- if $b64 -}}
true
{{- else -}}
{{- $inline := .Values.netappDrDiscoveryJson | default "" | trim }}
{{- if $inline -}}
true
{{- else -}}
{{- $disc := include "crossplane-aws-infra.discoveryDict" . | fromJson }}
{{- if $disc._discoveryComplete -}}
true
{{- end -}}
{{- end -}}
{{- end -}}
{{- end }}

{{- define "crossplane-aws-infra.fsxInstances" -}}
{{- $fsx := include "crossplane-aws-infra.mergedFsxOntap" . | fromJson }}
{{- $instances := list }}
{{- if and ($fsx.enabled | default false) (ne ($fsx.vpcId | default "") "") (ne ($fsx.fileSystemName | default "") "") }}
  {{- $local := dict
    "name" $fsx.fileSystemName
    "region" $fsx.region
    "storageCapacity" $fsx.storageCapacity
    "throughputCapacity" $fsx.throughputCapacity
    "storageType" $fsx.storageType
    "deploymentType" $fsx.deploymentType
    "vpcId" $fsx.vpcId
    "subnetIds" $fsx.subnetIds
    "routeTableIds" $fsx.routeTableIds
    "preferredSubnetId" ($fsx.preferredSubnetId | default (first $fsx.subnetIds))
    "allowedCidrs" $fsx.allowedCidrs
    "svmName" $fsx.svmName
    "rootVolumeSecurityStyle" $fsx.rootVolumeSecurityStyle
    "weeklyMaintenanceStartTime" $fsx.weeklyMaintenanceStartTime
    "automaticBackupRetentionDays" $fsx.automaticBackupRetentionDays
    "dailyAutomaticBackupStartTime" $fsx.dailyAutomaticBackupStartTime
    "tags" $fsx.tags
  }}
  {{- $instances = append $instances $local }}
{{- end }}
{{- $peer := $fsx.peer | default dict }}
{{- if and ($peer.enabled | default false) (ne ($peer.vpcId | default "") "") (ne ($peer.fileSystemName | default "") "") }}
  {{- $peerDict := dict
    "name" $peer.fileSystemName
    "region" $peer.region
    "storageCapacity" ($peer.storageCapacity | default $fsx.storageCapacity)
    "throughputCapacity" ($peer.throughputCapacity | default $fsx.throughputCapacity)
    "storageType" ($peer.storageType | default $fsx.storageType)
    "deploymentType" ($peer.deploymentType | default $fsx.deploymentType)
    "vpcId" $peer.vpcId
    "subnetIds" $peer.subnetIds
    "routeTableIds" $peer.routeTableIds
    "preferredSubnetId" ($peer.preferredSubnetId | default (first $peer.subnetIds))
    "allowedCidrs" $peer.allowedCidrs
    "svmName" $peer.svmName
    "rootVolumeSecurityStyle" ($peer.rootVolumeSecurityStyle | default $fsx.rootVolumeSecurityStyle)
    "weeklyMaintenanceStartTime" ($peer.weeklyMaintenanceStartTime | default $fsx.weeklyMaintenanceStartTime)
    "automaticBackupRetentionDays" ($peer.automaticBackupRetentionDays | default $fsx.automaticBackupRetentionDays)
    "dailyAutomaticBackupStartTime" ($peer.dailyAutomaticBackupStartTime | default $fsx.dailyAutomaticBackupStartTime)
    "tags" ($peer.tags | default $fsx.tags)
  }}
  {{- $instances = append $instances $peerDict }}
{{- end }}
{{- $instances | toJson }}
{{- end }}

{{/*
Standard FSx ONTAP security group rule definitions.
*/}}
{{- define "crossplane-aws-infra.sgRules" -}}
- name: icmp
  protocol: icmp
  from: -1
  to: -1
  desc: ICMP
- name: ssh
  protocol: tcp
  from: 22
  to: 22
  desc: SSH
- name: rpc-tcp
  protocol: tcp
  from: 111
  to: 111
  desc: RPC TCP
- name: rpc-udp
  protocol: udp
  from: 111
  to: 111
  desc: RPC UDP
- name: smb-135-tcp
  protocol: tcp
  from: 135
  to: 135
  desc: SMB/CIFS TCP 135
- name: smb-135-udp
  protocol: udp
  from: 135
  to: 135
  desc: SMB/CIFS UDP 135
- name: netbios-137-udp
  protocol: udp
  from: 137
  to: 137
  desc: NetBIOS UDP 137
- name: netbios-139-tcp
  protocol: tcp
  from: 139
  to: 139
  desc: NetBIOS TCP 139
- name: netbios-139-udp
  protocol: udp
  from: 139
  to: 139
  desc: NetBIOS UDP 139
- name: snmp-161-tcp
  protocol: tcp
  from: 161
  to: 161
  desc: SNMP TCP 161
- name: snmp-161-udp
  protocol: udp
  from: 161
  to: 161
  desc: SNMP UDP 161
- name: snmp-162-tcp
  protocol: tcp
  from: 162
  to: 162
  desc: SNMP Trap TCP 162
- name: snmp-162-udp
  protocol: udp
  from: 162
  to: 162
  desc: SNMP Trap UDP 162
- name: https
  protocol: tcp
  from: 443
  to: 443
  desc: HTTPS
- name: smb-445-tcp
  protocol: tcp
  from: 445
  to: 445
  desc: SMB TCP 445
- name: ontap-mount-tcp
  protocol: tcp
  from: 635
  to: 635
  desc: ONTAP Mount TCP 635
- name: ontap-mount-udp
  protocol: udp
  from: 635
  to: 635
  desc: ONTAP Mount UDP 635
- name: kerberos
  protocol: tcp
  from: 749
  to: 749
  desc: Kerberos
- name: nfs-tcp
  protocol: tcp
  from: 2049
  to: 2049
  desc: NFS TCP
- name: nfs-udp
  protocol: udp
  from: 2049
  to: 2049
  desc: NFS UDP
- name: iscsi
  protocol: tcp
  from: 3260
  to: 3260
  desc: iSCSI
- name: ontap-nlm-tcp
  protocol: tcp
  from: 4045
  to: 4045
  desc: ONTAP NLM TCP 4045
- name: ontap-nlm-udp
  protocol: udp
  from: 4045
  to: 4045
  desc: ONTAP NLM UDP 4045
- name: ontap-nsm-tcp
  protocol: tcp
  from: 4046
  to: 4046
  desc: ONTAP NSM TCP 4046
- name: ontap-nsm-udp
  protocol: udp
  from: 4046
  to: 4046
  desc: ONTAP NSM UDP 4046
- name: ontap-quota-udp
  protocol: udp
  from: 4049
  to: 4049
  desc: ONTAP Quota UDP 4049
- name: snapmirror-11104
  protocol: tcp
  from: 11104
  to: 11104
  desc: SnapMirror Intercluster 11104
- name: snapmirror-11105
  protocol: tcp
  from: 11105
  to: 11105
  desc: SnapMirror Intercluster 11105
{{- end }}
