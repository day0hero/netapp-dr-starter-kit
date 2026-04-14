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
Build the list of FSx instances to create (local + optional peer).
Returns a list of dicts, each with the full config for one FSx instance.
*/}}
{{- define "crossplane-aws-infra.fsxInstances" -}}
{{- $instances := list }}
{{- if .Values.fsxOntap.enabled }}
  {{- $local := dict
    "name" .Values.fsxOntap.fileSystemName
    "region" .Values.fsxOntap.region
    "storageCapacity" .Values.fsxOntap.storageCapacity
    "throughputCapacity" .Values.fsxOntap.throughputCapacity
    "storageType" .Values.fsxOntap.storageType
    "deploymentType" .Values.fsxOntap.deploymentType
    "vpcId" .Values.fsxOntap.vpcId
    "subnetIds" .Values.fsxOntap.subnetIds
    "routeTableIds" .Values.fsxOntap.routeTableIds
    "preferredSubnetId" (.Values.fsxOntap.preferredSubnetId | default (index .Values.fsxOntap.subnetIds 0))
    "allowedCidrs" .Values.fsxOntap.allowedCidrs
    "svmName" .Values.fsxOntap.svmName
    "rootVolumeSecurityStyle" .Values.fsxOntap.rootVolumeSecurityStyle
    "weeklyMaintenanceStartTime" .Values.fsxOntap.weeklyMaintenanceStartTime
    "automaticBackupRetentionDays" .Values.fsxOntap.automaticBackupRetentionDays
    "dailyAutomaticBackupStartTime" .Values.fsxOntap.dailyAutomaticBackupStartTime
    "tags" .Values.fsxOntap.tags
  }}
  {{- $instances = append $instances $local }}
{{- end }}
{{- if and ((.Values.fsxOntap.peer).enabled) ((.Values.fsxOntap.peer).fileSystemName) }}
  {{- $peer := dict
    "name" .Values.fsxOntap.peer.fileSystemName
    "region" .Values.fsxOntap.peer.region
    "storageCapacity" (.Values.fsxOntap.peer.storageCapacity | default .Values.fsxOntap.storageCapacity)
    "throughputCapacity" (.Values.fsxOntap.peer.throughputCapacity | default .Values.fsxOntap.throughputCapacity)
    "storageType" (.Values.fsxOntap.peer.storageType | default .Values.fsxOntap.storageType)
    "deploymentType" (.Values.fsxOntap.peer.deploymentType | default .Values.fsxOntap.deploymentType)
    "vpcId" .Values.fsxOntap.peer.vpcId
    "subnetIds" .Values.fsxOntap.peer.subnetIds
    "routeTableIds" .Values.fsxOntap.peer.routeTableIds
    "preferredSubnetId" (.Values.fsxOntap.peer.preferredSubnetId | default (index .Values.fsxOntap.peer.subnetIds 0))
    "allowedCidrs" .Values.fsxOntap.peer.allowedCidrs
    "svmName" .Values.fsxOntap.peer.svmName
    "rootVolumeSecurityStyle" (.Values.fsxOntap.peer.rootVolumeSecurityStyle | default .Values.fsxOntap.rootVolumeSecurityStyle)
    "weeklyMaintenanceStartTime" (.Values.fsxOntap.peer.weeklyMaintenanceStartTime | default .Values.fsxOntap.weeklyMaintenanceStartTime)
    "automaticBackupRetentionDays" (.Values.fsxOntap.peer.automaticBackupRetentionDays | default .Values.fsxOntap.automaticBackupRetentionDays)
    "dailyAutomaticBackupStartTime" (.Values.fsxOntap.peer.dailyAutomaticBackupStartTime | default .Values.fsxOntap.dailyAutomaticBackupStartTime)
    "tags" (.Values.fsxOntap.peer.tags | default .Values.fsxOntap.tags)
  }}
  {{- $instances = append $instances $peer }}
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
