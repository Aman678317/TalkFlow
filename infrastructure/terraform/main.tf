# Terraform skeleton — managed infrastructure for GlobalTalk AI production.
# Intentionally minimal & provider-pinned; fill in org-specific values via tfvars.
#
# Modules: VPC, EKS (CPU pool + GPU pool), RDS PostgreSQL, ElastiCache Redis,
# S3 + lifecycle policies, LiveKit on dedicated instances (or LiveKit Cloud),
# ACM cert, Route53, observability stack.

terraform {
  required_version = ">= 1.8"
  required_providers {
    aws = { source = "hashicorp/aws", version = "~> 5.60" }
  }
  backend "s3" {
    # bucket = "globaltalk-terraform-state"
    # key    = "prod/terraform.tfstate"
    # region = "ap-south-1"
  }
}

provider "aws" {
  region = var.region
  default_tags {
    tags = { Project = "globaltalk-ai", Environment = var.environment }
  }
}

variable "region" { type = string, default = "ap-south-1" }
variable "environment" { type = string, default = "prod" }
variable "vpc_cidr" { type = string, default = "10.40.0.0/16" }

# --- Data layer -------------------------------------------------------------
# RDS PostgreSQL 16 (Multi-AZ in prod), storage encrypted at rest (KMS).
# ElastiCache Redis 7 with at-rest + in-transit encryption, AUTH token from SSM.
# S3 bucket: SSE-KMS, versioning ON, lifecycle: audio/* expire per
# RETENTION_AUDIO_DAYS, documents/* per tenant policy, access logs 90d.
#
# --- Compute -----------------------------------------------------------------
# EKS 1.30:
#   node pool "general":  m7i.xlarge   x3 (api, web, cpu workers)
#   node pool "gpu":      g5.xlarge    x1..8 autoscaling (inference workers)
#   Karpenter for GPU scale-to-zero outside business hours (cost_optimized)
#
# --- Media -------------------------------------------------------------------
# LiveKit: dedicated g4dn instances behind NLB (UDP 7882 + TURN 443), or
# LiveKit Cloud with self-hosted agents. TURN co-located for NAT traversal.
#
# --- Observability -------------------------------------------------------------
# OpenTelemetry Collector DaemonSet -> Prometheus (AMP) + Grafana + Loki;
# Sentry via SENTRY_DSN secret. Alert rules in docs/operations/RUNBOOKS.md.

output "note" {
  value = "This skeleton documents the production topology; instantiate modules per org policy."
}
