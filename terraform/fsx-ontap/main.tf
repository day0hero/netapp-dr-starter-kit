# -----------------------------------------------------------------------------
# FSx for NetApp ONTAP Terraform Module
# -----------------------------------------------------------------------------

# Data source to get current AWS account ID
data "aws_caller_identity" "current" {}

# -----------------------------------------------------------------------------
# Security Group for FSx ONTAP
# -----------------------------------------------------------------------------
resource "aws_security_group" "fsx_ontap" {
  name        = "${var.file_system_name}-sg"
  description = "Security Group for FSx for NetApp ONTAP File Storage Access"
  vpc_id      = var.vpc_id

  tags = merge(var.tags, {
    Name = "${var.file_system_name}-sg"
  })
}

# ICMP
resource "aws_security_group_rule" "icmp" {
  type              = "ingress"
  from_port         = -1
  to_port           = -1
  protocol          = "icmp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "ICMP"
}

# SSH
resource "aws_security_group_rule" "ssh" {
  type              = "ingress"
  from_port         = 22
  to_port           = 22
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "SSH"
}

# NFS/RPC
resource "aws_security_group_rule" "rpc_tcp" {
  type              = "ingress"
  from_port         = 111
  to_port           = 111
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "RPC TCP"
}

resource "aws_security_group_rule" "rpc_udp" {
  type              = "ingress"
  from_port         = 111
  to_port           = 111
  protocol          = "udp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "RPC UDP"
}

# SMB/CIFS
resource "aws_security_group_rule" "smb_135_tcp" {
  type              = "ingress"
  from_port         = 135
  to_port           = 135
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "SMB/CIFS TCP 135"
}

resource "aws_security_group_rule" "smb_135_udp" {
  type              = "ingress"
  from_port         = 135
  to_port           = 135
  protocol          = "udp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "SMB/CIFS UDP 135"
}

resource "aws_security_group_rule" "smb_137_udp" {
  type              = "ingress"
  from_port         = 137
  to_port           = 137
  protocol          = "udp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "NetBIOS UDP 137"
}

resource "aws_security_group_rule" "smb_139_tcp" {
  type              = "ingress"
  from_port         = 139
  to_port           = 139
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "NetBIOS TCP 139"
}

resource "aws_security_group_rule" "smb_139_udp" {
  type              = "ingress"
  from_port         = 139
  to_port           = 139
  protocol          = "udp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "NetBIOS UDP 139"
}

resource "aws_security_group_rule" "smb_445_tcp" {
  type              = "ingress"
  from_port         = 445
  to_port           = 445
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "SMB TCP 445"
}

# SNMP
resource "aws_security_group_rule" "snmp_161_tcp" {
  type              = "ingress"
  from_port         = 161
  to_port           = 161
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "SNMP TCP 161"
}

resource "aws_security_group_rule" "snmp_161_udp" {
  type              = "ingress"
  from_port         = 161
  to_port           = 161
  protocol          = "udp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "SNMP UDP 161"
}

resource "aws_security_group_rule" "snmp_162_tcp" {
  type              = "ingress"
  from_port         = 162
  to_port           = 162
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "SNMP Trap TCP 162"
}

resource "aws_security_group_rule" "snmp_162_udp" {
  type              = "ingress"
  from_port         = 162
  to_port           = 162
  protocol          = "udp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "SNMP Trap UDP 162"
}

# HTTPS
resource "aws_security_group_rule" "https" {
  type              = "ingress"
  from_port         = 443
  to_port           = 443
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "HTTPS"
}

# NFS
resource "aws_security_group_rule" "nfs_tcp" {
  type              = "ingress"
  from_port         = 2049
  to_port           = 2049
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "NFS TCP"
}

resource "aws_security_group_rule" "nfs_udp" {
  type              = "ingress"
  from_port         = 2049
  to_port           = 2049
  protocol          = "udp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "NFS UDP"
}

# iSCSI
resource "aws_security_group_rule" "iscsi" {
  type              = "ingress"
  from_port         = 3260
  to_port           = 3260
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "iSCSI"
}

# ONTAP Management
resource "aws_security_group_rule" "ontap_4045_tcp" {
  type              = "ingress"
  from_port         = 4045
  to_port           = 4045
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "ONTAP NLM TCP 4045"
}

resource "aws_security_group_rule" "ontap_4045_udp" {
  type              = "ingress"
  from_port         = 4045
  to_port           = 4045
  protocol          = "udp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "ONTAP NLM UDP 4045"
}

resource "aws_security_group_rule" "ontap_4046_tcp" {
  type              = "ingress"
  from_port         = 4046
  to_port           = 4046
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "ONTAP NSM TCP 4046"
}

resource "aws_security_group_rule" "ontap_4046_udp" {
  type              = "ingress"
  from_port         = 4046
  to_port           = 4046
  protocol          = "udp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "ONTAP NSM UDP 4046"
}

resource "aws_security_group_rule" "ontap_4049_udp" {
  type              = "ingress"
  from_port         = 4049
  to_port           = 4049
  protocol          = "udp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "ONTAP Quota UDP 4049"
}

# Additional ONTAP ports
resource "aws_security_group_rule" "ontap_635_tcp" {
  type              = "ingress"
  from_port         = 635
  to_port           = 635
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "ONTAP Mount TCP 635"
}

resource "aws_security_group_rule" "ontap_635_udp" {
  type              = "ingress"
  from_port         = 635
  to_port           = 635
  protocol          = "udp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "ONTAP Mount UDP 635"
}

resource "aws_security_group_rule" "kerberos" {
  type              = "ingress"
  from_port         = 749
  to_port           = 749
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "Kerberos"
}

resource "aws_security_group_rule" "snapmirror_11104" {
  type              = "ingress"
  from_port         = 11104
  to_port           = 11104
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "SnapMirror Intercluster 11104"
}

resource "aws_security_group_rule" "snapmirror_11105" {
  type              = "ingress"
  from_port         = 11105
  to_port           = 11105
  protocol          = "tcp"
  cidr_blocks       = var.allowed_cidrs
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "SnapMirror Intercluster 11105"
}

# Egress rule - allow all outbound
resource "aws_security_group_rule" "egress_all" {
  type              = "egress"
  from_port         = 0
  to_port           = 0
  protocol          = "-1"
  cidr_blocks       = ["0.0.0.0/0"]
  security_group_id = aws_security_group.fsx_ontap.id
  description       = "Allow all outbound traffic"
}

# -----------------------------------------------------------------------------
# FSx for NetApp ONTAP File System
# -----------------------------------------------------------------------------
resource "aws_fsx_ontap_file_system" "this" {
  storage_capacity    = var.storage_capacity
  subnet_ids          = var.subnet_ids
  deployment_type     = var.deployment_type
  throughput_capacity = var.throughput_capacity
  storage_type        = var.storage_type
  security_group_ids  = [aws_security_group.fsx_ontap.id]

  # For MULTI_AZ_1, preferred_subnet_id must be specified
  preferred_subnet_id = var.deployment_type == "MULTI_AZ_1" ? var.subnet_ids[0] : null

  # Route table IDs are required for MULTI_AZ_1
  route_table_ids = var.deployment_type == "MULTI_AZ_1" ? var.route_table_ids : null

  fsx_admin_password                  = var.fsx_admin_password
  weekly_maintenance_start_time       = var.weekly_maintenance_time
  automatic_backup_retention_days     = var.automatic_backup_retention_days
  daily_automatic_backup_start_time   = var.daily_automatic_backup_start_time

  tags = merge(var.tags, {
    Name = var.file_system_name
  })

  lifecycle {
    prevent_destroy = false
  }
}

# -----------------------------------------------------------------------------
# Storage Virtual Machine (SVM)
# -----------------------------------------------------------------------------
resource "aws_fsx_ontap_storage_virtual_machine" "this" {
  file_system_id             = aws_fsx_ontap_file_system.this.id
  name                       = var.svm_name
  root_volume_security_style = var.root_volume_security_style
  svm_admin_password         = var.svm_admin_password

  tags = merge(var.tags, {
    Name = var.svm_name
  })
}

# -----------------------------------------------------------------------------
# AWS Secrets Manager - FSx Admin Password
# -----------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "fsx_admin" {
  count                   = var.create_secrets ? 1 : 0
  name                    = "${var.file_system_name}-FsxAdminPassword"
  description             = "FSx Admin Password for ${var.file_system_name}"
  recovery_window_in_days = 0

  tags = merge(var.tags, {
    Name = var.file_system_name
  })
}

resource "aws_secretsmanager_secret_version" "fsx_admin" {
  count     = var.create_secrets ? 1 : 0
  secret_id = aws_secretsmanager_secret.fsx_admin[0].id
  secret_string = jsonencode({
    username = "fsxadmin"
    password = var.fsx_admin_password
  })
}

# -----------------------------------------------------------------------------
# AWS Secrets Manager - SVM Admin Password
# -----------------------------------------------------------------------------
resource "aws_secretsmanager_secret" "svm_admin" {
  count                   = var.create_secrets ? 1 : 0
  name                    = "${var.file_system_name}-SVMAdminPassword"
  description             = "SVM Admin Password for ${var.file_system_name}"
  recovery_window_in_days = 0

  tags = merge(var.tags, {
    Name = var.file_system_name
  })
}

resource "aws_secretsmanager_secret_version" "svm_admin" {
  count     = var.create_secrets ? 1 : 0
  secret_id = aws_secretsmanager_secret.svm_admin[0].id
  secret_string = jsonencode({
    username = "vsadmin"
    password = var.svm_admin_password
  })
}
