#!/usr/bin/env bash
# ==============================================================================
# Desi / GlobalTalk AI — Compute Engine Automated Deployment Script (Bash)
#
# Authenticates programmatically using Google Cloud CLI (gcloud) and provisions:
# 1. Dedicated Service Account with least-privilege IAM roles
# 2. VPC Firewall rule for port 8088 (Desi API Gateway)
# 3. Compute Engine VM running Ubuntu 22.04 with attached Service Account
# ==============================================================================

set -euo pipefail

PROJECT_ID="${1:-$(gcloud config get-value project 2>/dev/null || echo "")}"
ZONE="${2:-asia-south1-a}"
INSTANCE_NAME="${3:-desi-ai-instance}"
MACHINE_TYPE="${4:-e2-standard-4}"
SA_NAME="${5:-desi-engine-sa}"

echo "=================================================================="
echo "     Desi Language AI — Google Cloud Compute Engine Deployer      "
echo "=================================================================="

if [[ -z "${PROJECT_ID}" || "${PROJECT_ID}" == "(unset)" ]]; then
    echo "Error: No active GCP project found. Run: ./deploy_compute_engine.sh <PROJECT_ID>" >&2
    exit 1
fi

echo "  GCP Project:   ${PROJECT_ID}"
echo "  Target Zone:   ${ZONE}"
echo "  Instance Name: ${INSTANCE_NAME}"
echo "  Machine Type:  ${MACHINE_TYPE}"

echo -e "\n[1/5] Enabling Compute Engine & IAM APIs..."
gcloud services enable compute.googleapis.com iam.googleapis.com cloudresourcemanager.googleapis.com --project "${PROJECT_ID}"

echo -e "\n[2/5] Setting up Dedicated Service Account..."
SA_EMAIL="${SA_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

if ! gcloud iam service-accounts describe "${SA_EMAIL}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud iam service-accounts create "${SA_NAME}" \
        --description="Service account for Desi AI Compute Engine VM" \
        --display-name="Desi Engine Service Account" \
        --project "${PROJECT_ID}"
else
    echo "  Service account ${SA_EMAIL} already exists."
fi

ROLES=(
    "roles/logging.logWriter"
    "roles/monitoring.metricWriter"
    "roles/storage.objectViewer"
)

for role in "${ROLES[@]}"; do
    echo "  Binding role: ${role}"
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="${role}" \
        --condition=None \
        --quiet >/dev/null
done

echo -e "\n[3/5] Configuring VPC Firewall Rule for Port 8088..."
FW_RULE="allow-desi-gateway-8088"
if ! gcloud compute firewall-rules describe "${FW_RULE}" --project "${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud compute firewall-rules create "${FW_RULE}" \
        --allow=tcp:8088,tcp:80,tcp:443 \
        --target-tags="desi-gateway" \
        --description="Allow inbound HTTP traffic to Desi Language AI Gateway" \
        --project "${PROJECT_ID}"
else
    echo "  Firewall rule ${FW_RULE} already exists."
fi

echo -e "\n[4/5] Provisioning Compute Engine VM Instance..."
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STARTUP_SCRIPT="${SCRIPT_DIR}/startup.sh"

if ! gcloud compute instances describe "${INSTANCE_NAME}" --zone="${ZONE}" --project="${PROJECT_ID}" >/dev/null 2>&1; then
    gcloud compute instances create "${INSTANCE_NAME}" \
        --project="${PROJECT_ID}" \
        --zone="${ZONE}" \
        --machine-type="${MACHINE_TYPE}" \
        --image-family=ubuntu-2204-lts \
        --image-project=ubuntu-os-cloud \
        --boot-disk-size=50GB \
        --boot-disk-type=pd-balanced \
        --tags=desi-gateway,http-server,https-server \
        --service-account="${SA_EMAIL}" \
        --scopes=cloud-platform \
        --metadata-from-file=startup-script="${STARTUP_SCRIPT}"
else
    echo "  Instance ${INSTANCE_NAME} already exists in ${ZONE}."
fi

echo -e "\n[5/5] Fetching Public IP and Access Information..."
sleep 5
PUBLIC_IP=$(gcloud compute instances describe "${INSTANCE_NAME}" \
    --zone="${ZONE}" \
    --project="${PROJECT_ID}" \
    --format="value(networkInterfaces[0].accessConfigs[0].natIP)")

echo "=================================================================="
echo "             Deployment Successfully Initiated!                   "
echo "=================================================================="
echo "Instance:         ${INSTANCE_NAME}"
echo "Zone:             ${ZONE}"
echo "Service Account:  ${SA_EMAIL}"
echo "Public IP:        ${PUBLIC_IP}"
echo "Desi Gateway URL: http://${PUBLIC_IP}:8088"
echo "API Docs:         http://${PUBLIC_IP}:8088/docs"
echo ""
echo "Test connection once initialization completes:"
echo "  curl -X GET \"http://${PUBLIC_IP}:8088/v2/desi/languages\""
echo "=================================================================="
