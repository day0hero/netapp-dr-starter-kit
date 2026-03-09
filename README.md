# NetApp DR Starter Kit

[![License](https://img.shields.io/badge/License-Apache%202.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)

Automated DR infrastructure setup for OpenShift clusters using FSx for NetApp ONTAP
and Trident Protect. Given two cluster kubeconfigs (production and DR), this toolkit:

1. **Discovers** cluster info (VPC, CIDR, region) from each cluster's API
2. **Peers the VPCs** across regions so the clusters can communicate
3. **Creates FSx for NetApp ONTAP** filesystems in each region (named `$CLUSTER-$REGION-fsx`)
4. Outputs the configuration needed for **Trident / Trident Protect** DR replication

## Prerequisites

- Two OpenShift clusters on AWS (in different regions for cross-region DR)
- Kubeconfig files for both clusters
- **Terraform** >= 1.0.0
- **Ansible** with collections: `amazon.aws`, `kubernetes.core`
- **AWS CLI** configured with credentials that have permissions for:
  FSx, EC2 (VPC peering, security groups, route tables), Secrets Manager
- **Python3** with `boto3` and `kubernetes` packages
- (Optional) `~/.fsx` file containing the FSx/SVM admin password

## Quick Start

```bash
# Install Ansible collections
ansible-galaxy collection install -r ansible/ansible-requirements.yml

# Build complete DR infrastructure
make build-dr \
  PROD_KUBECONFIG=~/kubeconfig-prod \
  DR_KUBECONFIG=~/kubeconfig-dr

# Destroy everything
make destroy-dr \
  PROD_KUBECONFIG=~/kubeconfig-prod \
  DR_KUBECONFIG=~/kubeconfig-dr
```

## What Gets Auto-Detected

For each cluster, the following values are looked up automatically from the Kubernetes API
(all can be overridden via variables):

| Value | Source | Override Variable |
| ----- | ------ | ----------------- |
| Cluster name | `infrastructure/cluster .status.infrastructureName` | `PROD_CLUSTER` / `DR_CLUSTER` |
| AWS region | `infrastructure/cluster .status.platformStatus.aws.region` | `PROD_REGION` / `DR_REGION` |
| VPC CIDR | `cm/cluster-config-v1` in `kube-system` (networking.machineNetwork) | `PROD_VPC_CIDR` / `DR_VPC_CIDR` |
| VPC name | Derived from infrastructure name (`<infra-name>-vpc`) | `-e prod_vpc_name_override=...` |

## Make Targets

| Target | Description |
| ------ | ----------- |
| `make build-dr` | Build complete DR infrastructure (VPC peering + FSx in both regions) |
| `make destroy-dr` | Destroy all DR infrastructure |
| `make setup-terraform-state` | Create S3 bucket for Terraform state storage |
| `make destroy-terraform-state` | Delete Terraform state S3 bucket |

### Required Variables

| Variable | Description |
| -------- | ----------- |
| `PROD_KUBECONFIG` | Path to production cluster kubeconfig |
| `DR_KUBECONFIG` | Path to DR cluster kubeconfig |

### Optional Overrides

| Variable | Description |
| -------- | ----------- |
| `PROD_CLUSTER` | Production cluster infrastructure name |
| `DR_CLUSTER` | DR cluster infrastructure name |
| `PROD_REGION` | Production AWS region |
| `DR_REGION` | DR AWS region |
| `PROD_VPC_CIDR` | Production VPC CIDR block |
| `DR_VPC_CIDR` | DR VPC CIDR block |
| `TERRAFORM_STATE_BUCKET` | S3 bucket for Terraform state (recommended for production) |

## Architecture

```text
┌─────────────────────────────┐          ┌─────────────────────────────┐
│   Production Region         │          │   DR Region                 │
│                             │          │                             │
│  ┌───────────────────────┐  │  VPC     │  ┌───────────────────────┐  │
│  │  OpenShift Cluster    │  │ Peering  │  │  OpenShift Cluster    │  │
│  │  (with Trident)       │◄─┼──────────┼─►│  (with Trident)       │  │
│  └───────────────────────┘  │          │  └───────────────────────┘  │
│                             │          │                             │
│  ┌───────────────────────┐  │ SnapMir  │  ┌───────────────────────┐  │
│  │ FSx for NetApp ONTAP  │  │  ror     │  │ FSx for NetApp ONTAP  │  │
│  │ $CLUSTER-$REGION-fsx  │◄─┼──────────┼─►│ $CLUSTER-$REGION-fsx  │  │
│  └───────────────────────┘  │          │  └───────────────────────┘  │
│                             │          │                             │
└─────────────────────────────┘          └─────────────────────────────┘
```

## Password Management

FSx and SVM admin passwords can be provided via:

1. **`~/.fsx` file** (recommended):

   ```bash
   echo "MySecurePassword123!" > ~/.fsx
   chmod 600 ~/.fsx
   ```

2. **Command line**:

   ```bash
   make build-dr ... EXTRA_PLAYBOOK_OPTS="-e fsx_admin_password=MyPassword -e svm_admin_password=MyPassword"
   ```

## Terraform State

By default, Terraform state is stored locally in `/tmp/netapp-dr-terraform/`.
For production use, configure S3 backend:

```bash
# Create S3 bucket for state
make setup-terraform-state PROD_KUBECONFIG=~/kubeconfig-prod TERRAFORM_STATE_BUCKET=my-tf-state

# Use S3 backend for all operations
make build-dr ... TERRAFORM_STATE_BUCKET=my-tf-state
```

State is scoped per component and cluster:

- VPC peering: `vpc-peering/terraform.tfstate`
- Prod FSx: `fsx-ontap/<cluster>/<region>/terraform.tfstate`
- DR FSx: `fsx-ontap/<cluster>/<region>/terraform.tfstate`

## Project Structure

```text
├── ansible/
│   ├── dr-setup.yaml              # Main playbook
│   ├── dr-vars.yml                # Default variables
│   ├── ansible-requirements.yml   # Ansible collection dependencies
│   └── roles/
│       ├── cluster_discovery/     # Queries cluster for VPC, CIDR, region
│       ├── vpc_peering_terraform/ # Peers VPCs via Terraform
│       └── fsx_ontap_terraform/   # Creates FSx ONTAP via Terraform
├── terraform/
│   ├── fsx-ontap/                 # FSx for NetApp ONTAP module
│   │   ├── main.tf               # SG + FSx filesystem + SVM + Secrets
│   │   ├── variables.tf
│   │   ├── outputs.tf
│   │   └── providers.tf
│   └── vpc-peering/               # Cross-region VPC peering module
│       ├── main.tf                # Peering connection + routes + DNS
│       ├── variables.tf
│       ├── outputs.tf
│       └── providers.tf
├── scripts/
│   └── setup-terraform-state-s3.sh
├── Makefile
└── README.md
```

## Next Steps After Setup

Once the infrastructure is created:

1. **Install Trident** on both clusters
2. **Configure Trident backends** using the SVM management DNS names from the output
3. **Install Trident Protect** and configure `AppMirrorRelationship` CRs for cross-region
   DR replication using the FSx intercluster endpoints
