#!/bin/bash
# Fallback: delete FSx ONTAP + inter-region VPC peering from AWS when Crossplane
# oc delete did not remove external resources. Env vars required (see crossplane-destroy.yaml).
set -u
set -o pipefail

: "${PROD_REGION:?}" "${DR_REGION:?}" "${PROD_FSX_NAME:?}" "${DR_FSX_NAME:?}"
: "${PROD_CLUSTER_NAME:?}" "${DR_CLUSTER_NAME:?}"
PROD_VPC_ID="${PROD_VPC_ID:-}"
DR_VPC_ID="${DR_VPC_ID:-}"
PEERING_NAME="${PEERING_NAME:-${PROD_CLUSTER_NAME}-to-${DR_CLUSTER_NAME}}"
AWS=(aws --no-cli-pager)

# JMESPath tag filters on describe-file-systems often miss matches; scan in Python.
fsx_id_by_name() {
  local REGION="$1"
  local NAME="$2"
  FSX_LOOKUP_NAME="${NAME}" "${AWS[@]}" fsx describe-file-systems \
    --region "${REGION}" --output json 2>/dev/null | python3 -c "
import json, os
name = os.environ['FSX_LOOKUP_NAME']
for fs in json.load(sys.stdin).get('FileSystems', []):
    tags = {t['Key']: t['Value'] for t in fs.get('Tags', [])}
    if tags.get('Name') == name:
        print(fs['FileSystemId'])
        break
" 2>/dev/null | tr -d '\r'
}

find_vpc_peering_id() {
  local REGION="$1"
  local PCX=""
  PCX=$("${AWS[@]}" ec2 describe-vpc-peering-connections --region "${REGION}" \
    --filters "Name=tag:Name,Values=${PEERING_NAME}" \
    --query "VpcPeeringConnections[?Status.Code!='deleted'].VpcPeeringConnectionId | [0]" \
    --output text 2>/dev/null | tr -d '\r' || true)
  if [ -n "${PCX}" ] && [ "${PCX}" != "None" ]; then
    echo "${PCX}"
    return 0
  fi
  if [ -z "${PROD_VPC_ID}" ] || [ -z "${DR_VPC_ID}" ]; then
    return 1
  fi
  for REQ in "${PROD_VPC_ID}" "${DR_VPC_ID}"; do
    for ACC in "${DR_VPC_ID}" "${PROD_VPC_ID}"; do
      [ "${REQ}" = "${ACC}" ] && continue
      PCX=$("${AWS[@]}" ec2 describe-vpc-peering-connections --region "${REGION}" \
        --filters \
          "Name=requester-vpc-info.vpc-id,Values=${REQ}" \
          "Name=accepter-vpc-info.vpc-id,Values=${ACC}" \
        --query "VpcPeeringConnections[?Status.Code!='deleted'].VpcPeeringConnectionId | [0]" \
        --output text 2>/dev/null | tr -d '\r' || true)
      if [ -n "${PCX}" ] && [ "${PCX}" != "None" ]; then
        echo "${PCX}"
        return 0
      fi
    done
  done
  return 1
}

echo "=========================================="
echo "AWS fallback destroy"
echo "  FSx: ${PROD_FSX_NAME} (${PROD_REGION}), ${DR_FSX_NAME} (${DR_REGION})"
echo "  Peering tag Name: ${PEERING_NAME}"
echo "=========================================="

delete_non_root_volumes() {
  local REGION="$1"
  local FS_ID="$2"
  local VOL_IDS
  VOL_IDS=$("${AWS[@]}" fsx describe-volumes --region "${REGION}" \
    --filters "Name=file-system-id,Values=${FS_ID}" \
    --query "Volumes[?OntapConfiguration.StorageVirtualMachineRoot!=\`true\`].VolumeId" \
    --output text 2>/dev/null || true)
  for VID in ${VOL_IDS}; do
    [ -z "${VID}" ] || [ "${VID}" = "None" ] && continue
    echo "  delete-volume ${VID}..."
    "${AWS[@]}" fsx delete-volume --region "${REGION}" --volume-id "${VID}" \
      --ontap-configuration '{"SkipFinalBackup":true}' 2>/dev/null || true
  done
  for _ in $(seq 1 36); do
    R=$("${AWS[@]}" fsx describe-volumes --region "${REGION}" \
      --filters "Name=file-system-id,Values=${FS_ID}" \
      --query "length(Volumes[?OntapConfiguration.StorageVirtualMachineRoot!=\`true\` && Lifecycle!=\`DELETED\` && Lifecycle!=\`FAILED\`])" \
      --output text 2>/dev/null || echo 99)
    [ "${R}" = "0" ] || [ "${R}" = "None" ] && break
    sleep 10
  done
}

delete_svms_for_fs() {
  local REGION="$1"
  local FS_ID="$2"
  local SVM_IDS
  SVM_IDS=$("${AWS[@]}" fsx describe-storage-virtual-machines --region "${REGION}" \
    --filters "Name=file-system-id,Values=${FS_ID}" \
    --query "StorageVirtualMachines[].StorageVirtualMachineId" --output text 2>/dev/null || true)
  for SVM in ${SVM_IDS}; do
    [ -z "${SVM}" ] || [ "${SVM}" = "None" ] && continue
    echo "  delete-storage-virtual-machine ${SVM}..."
    "${AWS[@]}" fsx delete-storage-virtual-machine --region "${REGION}" \
      --storage-virtual-machine-id "${SVM}" 2>/dev/null || true
  done
  for _ in $(seq 1 60); do
    R=$("${AWS[@]}" fsx describe-storage-virtual-machines --region "${REGION}" \
      --filters "Name=file-system-id,Values=${FS_ID}" \
      --query "length(StorageVirtualMachines[?Lifecycle!=\`DELETED\` && Lifecycle!=\`FAILED\` && Lifecycle!=\`MISCONFIGURED\`])" \
      --output text 2>/dev/null || echo 99)
    [ "${R}" = "0" ] || [ "${R}" = "None" ] && break
    sleep 10
  done
}

wait_fsx_gone() {
  local REGION="$1"
  local NAME="$2"
  local FS_ID
  for _ in $(seq 1 90); do
    FS_ID=$(fsx_id_by_name "${REGION}" "${NAME}")
    if [ -z "${FS_ID}" ] || [ "${FS_ID}" = "None" ] || [ "${FS_ID}" = "null" ]; then
      return 0
    fi
    sleep 20
  done
  return 1
}

delete_fsx_by_name() {
  local REGION="$1"
  local NAME="$2"
  local LABEL="$3"
  local FS_ID
  FS_ID=$(fsx_id_by_name "${REGION}" "${NAME}")
  if [ -z "${FS_ID}" ] || [ "${FS_ID}" = "None" ] || [ "${FS_ID}" = "null" ]; then
    echo "No FSx filesystem tagged Name=${NAME} in ${REGION} (${LABEL})"
    return 0
  fi
  echo ">>> ${LABEL}: deleting FSx ${FS_ID} (${NAME}) in ${REGION}"
  delete_non_root_volumes "${REGION}" "${FS_ID}"
  delete_svms_for_fs "${REGION}" "${FS_ID}"
  echo "  delete-file-system ${FS_ID}..."
  "${AWS[@]}" fsx delete-file-system --region "${REGION}" --file-system-id "${FS_ID}" \
    --ontap-configuration '{"SkipFinalBackup":true}' 2>/dev/null || \
  "${AWS[@]}" fsx delete-file-system --region "${REGION}" --file-system-id "${FS_ID}" 2>/dev/null || true
  if ! wait_fsx_gone "${REGION}" "${NAME}"; then
    echo "VERIFY_FAIL: FSx ${NAME} still present in ${REGION} after delete wait"
    return 2
  fi
  return 0
}

delete_routes_for_pcx() {
  local REGION="$1"
  local VPC_ID="$2"
  local PCX="$3"
  [ -z "${VPC_ID}" ] && return 0
  local RT_IDS
  RT_IDS=$("${AWS[@]}" ec2 describe-route-tables --region "${REGION}" \
    --filters "Name=vpc-id,Values=${VPC_ID}" \
    --query "RouteTables[].RouteTableId" --output text 2>/dev/null || true)
  for RTB in ${RT_IDS}; do
    [ -z "${RTB}" ] && continue
    DESTS=$("${AWS[@]}" ec2 describe-route-tables --region "${REGION}" --route-table-ids "${RTB}" \
      --query "RouteTables[0].Routes[?VpcPeeringConnectionId==\`${PCX}\`].DestinationCidrBlock" \
      --output text 2>/dev/null || true)
    for D in ${DESTS}; do
      [ -z "${D}" ] && continue
      echo "  delete-route ${RTB} ${D} (pcx ${PCX})..."
      "${AWS[@]}" ec2 delete-route --region "${REGION}" --route-table-id "${RTB}" \
        --destination-cidr-block "${D}" 2>/dev/null || true
    done
  done
}

delete_vpc_peering() {
  local PCX
  PCX=$(find_vpc_peering_id "${PROD_REGION}" || true)
  if [ -z "${PCX}" ] || [ "${PCX}" = "None" ]; then
    echo "No active VPC peering found (Name=${PEERING_NAME}, VPCs ${PROD_VPC_ID:-?} <-> ${DR_VPC_ID:-?})"
    return 0
  fi
  echo ">>> Deleting VPC peering ${PCX}"
  delete_routes_for_pcx "${PROD_REGION}" "${PROD_VPC_ID}" "${PCX}"
  delete_routes_for_pcx "${DR_REGION}" "${DR_VPC_ID}" "${PCX}"
  "${AWS[@]}" ec2 delete-vpc-peering-connection --region "${PROD_REGION}" \
    --vpc-peering-connection-id "${PCX}" 2>/dev/null || true
  for _ in $(seq 1 30); do
    ST=$("${AWS[@]}" ec2 describe-vpc-peering-connections --region "${PROD_REGION}" \
      --vpc-peering-connection-ids "${PCX}" \
      --query "VpcPeeringConnections[0].Status.Code" --output text 2>/dev/null || echo gone)
    [ "${ST}" = "deleted" ] || [ "${ST}" = "gone" ] || [ "${ST}" = "None" ] && break
    sleep 5
  done
  return 0
}

RC=0
PEER_RC=0
delete_fsx_by_name "${PROD_REGION}" "${PROD_FSX_NAME}" "Production" || RC=$?
delete_fsx_by_name "${DR_REGION}" "${DR_FSX_NAME}" "DR" || RC=$?
delete_vpc_peering || PEER_RC=$?

echo ">>> Final verification"
REM_P=$(fsx_id_by_name "${PROD_REGION}" "${PROD_FSX_NAME}")
REM_D=$(fsx_id_by_name "${DR_REGION}" "${DR_FSX_NAME}")
PCX_LEFT=$(find_vpc_peering_id "${PROD_REGION}" || true)
if [ -n "${REM_P}" ] && [ "${REM_P}" != "None" ]; then echo "VERIFY_FAIL: Production FSx still exists: ${REM_P}"; exit 2; fi
if [ -n "${REM_D}" ] && [ "${REM_D}" != "None" ]; then echo "VERIFY_FAIL: DR FSx still exists: ${REM_D}"; exit 2; fi
if [ "${RC}" != "0" ]; then echo "VERIFY_FAIL: FSx delete reported errors (rc=${RC})"; exit 2; fi
if [ "${PEER_RC}" != "0" ]; then echo "VERIFY_FAIL: VPC peering delete reported errors (rc=${PEER_RC})"; exit 2; fi
if [ -n "${PCX_LEFT}" ] && [ "${PCX_LEFT}" != "None" ]; then
  echo "VERIFY_FAIL: VPC peering still active: ${PCX_LEFT}"
  exit 2
fi

echo "AWS fallback verification OK"
exit 0
