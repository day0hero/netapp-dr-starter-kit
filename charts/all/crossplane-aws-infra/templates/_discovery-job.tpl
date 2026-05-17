{{/*
Shared discovery Job container spec (CronJob, initial Job, post-sync Job).
*/}}
{{- define "crossplane-aws-infra.discoveryJobPodSpec" -}}
{{- $root := .root }}
{{- $b := .bootstrap }}
{{- $argo := $b.argocd | default dict }}
{{- $p1 := $argo.patchApplication | default dict }}
{{- $p2 := $argo.patchDrDnsApplication | default dict }}
{{- $argoNs := "openshift-gitops" }}
{{- if $p1.applicationNamespace }}
{{- $argoNs = $p1.applicationNamespace }}
{{- else if $root.Values.global.pattern }}
{{- $argoNs = printf "%s-hub" $root.Values.global.pattern }}
{{- end }}
{{- $drDnsNs := $argoNs }}
{{- if $p2.applicationNamespace }}
{{- $drDnsNs = $p2.applicationNamespace }}
{{- end }}
restartPolicy: Never
serviceAccountName: crossplane-network-discovery
containers:
  - name: discover
    image: {{ $root.Values.endpointWatcher.image | quote }}
    command: ["python3", "/scripts/discover-network.py"]
    env:
      - name: DISCOVERY_HOOK
        value: {{ .discoveryHook | default "" | quote }}
      - name: PATTERN_CLUSTER_ROLE
        value: {{ $root.Values.clusterGroup.name | default "hub" | quote }}
      - name: REMOTE_KUBECONFIG_PATH
        value: /peer/kubeconfig
      - name: DISCOVERY_CONFIGMAP_NAMESPACE
        value: {{ $b.discoveryNamespace | default $root.Release.Namespace | quote }}
      - name: DISCOVERY_CONFIGMAP_NAME
        value: {{ $b.discoveryConfigMapName | default "crossplane-network-discovery" | quote }}
      - name: TARGET_NAMESPACE
        value: {{ $root.Release.Namespace | quote }}
      - name: AWS_SHARED_CREDENTIALS_FILE
        value: /aws/credentials
      - name: AWS_EC2_METADATA_DISABLED
        value: "true"
      - name: APPVAULT_BUCKET
        value: {{ ($root.Values.tridentProtect.appVault.s3.bucketName) | default "" | quote }}
      - name: APPVAULT_REGION
        value: {{ ($root.Values.tridentProtect.appVault.s3.region) | default "" | quote }}
      - name: DR_FAILOVER_DOMAIN
        value: {{ ($root.Values.drFailover.domain) | default "" | quote }}
      - name: ROUTE53_DISCOVER_HOSTED_ZONE
        value: {{ $b.route53.discoverHostedZone | default true | toString | quote }}
      - name: ROUTE53_DISCOVER_HOSTED_ZONE_PARENT
        value: {{ $b.route53.discoverHostedZoneParent | default true | toString | quote }}
      - name: ROUTE53_ZONE_LOOKUP_NAME
        value: {{ $b.route53.zoneLookupName | default "" | quote }}
      - name: ROUTE53_HOSTED_ZONE_ID_EXPLICIT
        value: {{ $root.Values.route53Failover.hostedZoneId | default "" | quote }}
      - name: ROUTE53_CREATE_HOSTED_ZONE
        value: {{ $root.Values.route53Failover.createHostedZone | default true | toString | quote }}
      - name: PATCH_ARGOCD_CROSSPLANE_APP
        value: {{ $p1.enabled | default false | toString | quote }}
      - name: PATCH_ARGOCD_DR_DNS_APP
        value: {{ $p2.enabled | default false | toString | quote }}
      - name: ARGOCD_APPLICATION_NAMESPACE
        value: {{ $argoNs | quote }}
      - name: ARGOCD_CHILD_APPLICATION_NAMESPACE
        value: {{ $argoNs | quote }}
      - name: ARGOCD_APPLICATION_NAME
        value: {{ $p1.applicationName | default "" | quote }}
      - name: PATCH_ARGOCD_AUTO
        value: {{ $p1.autoDiscover | default true | toString | quote }}
      - name: ARGOCD_DR_DNS_APPLICATION_NAMESPACE
        value: {{ $drDnsNs | quote }}
      - name: ARGOCD_DR_DNS_APPLICATION_NAME
        value: {{ $p2.applicationName | default "" | quote }}
      - name: PATCH_ARGOCD_DR_DNS_AUTO
        value: {{ $p2.autoDiscover | default true | toString | quote }}
      - name: GLOBAL_PATTERN
        value: {{ $root.Values.global.pattern | quote }}
      - name: CLUSTER_GROUP_NAME
        value: {{ $root.Values.clusterGroup.name | default "hub" | quote }}
      - name: PATCH_ARGOCD_PARENT_IGNORE_DIFFERENCES
        value: {{ ternary "true" "false" (and ($p1.enabled | default false) ($p1.parentIgnoreDifferences | default true)) | quote }}
      - name: RETRY_VPC_PEERING_OPTIONS
        value: "true"
      - name: ARGOCD_PARENT_APPLICATION_NAMESPACE
        value: {{ ($p1.parentApplicationNamespace | default "vp-gitops") | quote }}
      - name: ARGOCD_PARENT_APPLICATION_NAME
        value: {{ $p1.parentApplicationName | default "" | quote }}
      - name: TRIGGER_ARGO_RESYNC
        value: {{ .triggerResync | default "false" | quote }}
    volumeMounts:
      - name: scripts
        mountPath: /scripts
        readOnly: true
      - name: aws-creds
        mountPath: /aws
        readOnly: true
      {{- if ne (.discoveryHook | default "") "postsync" }}
      - name: peer-kubeconfig
        mountPath: /peer
        readOnly: true
      {{- end }}
volumes:
  - name: scripts
    configMap:
      name: crossplane-bootstrap-scripts
      defaultMode: 0555
      items:
        - key: discover-network.py
          path: discover-network.py
  {{- if ne (.discoveryHook | default "") "postsync" }}
  - name: aws-creds
    secret:
      secretName: {{ $root.Values.crossplane.providerConfig.credentials.secretName }}
      items:
        - key: {{ $root.Values.crossplane.providerConfig.credentials.secretKey }}
          path: credentials
  - name: peer-kubeconfig
    secret:
      secretName: {{ $b.remoteKubeconfig.secretName }}
      optional: {{ $b.remoteKubeconfig.optional | default true }}
      items:
        - key: {{ $b.remoteKubeconfig.secretKey }}
          path: kubeconfig
  {{- else }}
  - name: aws-creds
    secret:
      secretName: {{ $root.Values.crossplane.providerConfig.credentials.secretName }}
      optional: true
      items:
        - key: {{ $root.Values.crossplane.providerConfig.credentials.secretKey }}
          path: credentials
  {{- end }}
{{- end }}
