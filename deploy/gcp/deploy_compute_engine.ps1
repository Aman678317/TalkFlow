# ==============================================================================
# Desi / GlobalTalk AI — Compute Engine Automated Deployment Script (PowerShell)
#
# Authenticates programmatically using Google Cloud CLI (gcloud) and provisions:
# 1. Dedicated Service Account with least-privilege IAM roles
# 2. VPC Firewall rule for port 8088 (Desi API Gateway)
# 3. Compute Engine VM running Ubuntu 22.04 with attached Service Account
# ==============================================================================

[CmdletBinding()]
param (
    [string]$ProjectId,
    [string]$Zone = "asia-south1-a",
    [string]$InstanceName = "desi-ai-instance",
    [string]$MachineType = "e2-standard-4",
    [string]$ServiceAccountName = "desi-engine-sa"
)

$ErrorActionPreference = "Stop"

Write-Host "==================================================================" -ForegroundColor Cyan
Write-Host "     Desi Language AI — Google Cloud Compute Engine Deployer      " -ForegroundColor Cyan
Write-Host "==================================================================" -ForegroundColor Cyan

# 1. Check gcloud CLI
Write-Host "`n[1/6] Verifying Google Cloud CLI installation..." -ForegroundColor Yellow
if (-not (Get-Command gcloud -ErrorAction SilentlyContinue)) {
    Write-Error "Google Cloud CLI (gcloud) is not installed or not in PATH. Please install from https://cloud.google.com/sdk/docs/install"
    exit 1
}

# Resolve active project if not explicitly specified
if ([string]::IsNullOrWhiteSpace($ProjectId)) {
    $ProjectId = (gcloud config get-value project 2>$null).Trim()
    if ([string]::IsNullOrWhiteSpace($ProjectId) -or $ProjectId -eq "(unset)") {
        Write-Error "No active GCP project found. Specify -ProjectId <YOUR_PROJECT_ID> or run 'gcloud config set project <PROJECT_ID>'."
        exit 1
    }
}
Write-Host "  Using GCP Project: $ProjectId" -ForegroundColor Green
Write-Host "  Target Zone:       $Zone" -ForegroundColor Green
Write-Host "  Instance Name:     $InstanceName" -ForegroundColor Green
Write-Host "  Machine Type:      $MachineType" -ForegroundColor Green

# 2. Enable Required APIs
Write-Host "`n[2/6] Enabling Compute Engine & IAM APIs..." -ForegroundColor Yellow
gcloud services enable compute.googleapis.com iam.googleapis.com cloudresourcemanager.googleapis.com --project $ProjectId

# 3. Create Service Account
Write-Host "`n[3/6] Setting up Dedicated Service Account..." -ForegroundColor Yellow
$saEmail = "$ServiceAccountName@$ProjectId.iam.gserviceaccount.com"
$existingSa = gcloud iam service-accounts list --filter="email=$saEmail" --format="value(email)" --project $ProjectId 2>$null

if (-not $existingSa) {
    Write-Host "  Creating service account: $saEmail" -ForegroundColor Gray
    gcloud iam service-accounts create $ServiceAccountName `
        --description="Service account for Desi AI Compute Engine VM" `
        --display-name="Desi Engine Service Account" `
        --project $ProjectId
} else {
    Write-Host "  Service account already exists: $saEmail" -ForegroundColor Gray
}

# Grant necessary IAM roles (Monitoring, Logging, Storage)
$roles = @(
    "roles/logging.logWriter",
    "roles/monitoring.metricWriter",
    "roles/storage.objectViewer"
)

foreach ($role in $roles) {
    Write-Host "  Granting role: $role" -ForegroundColor Gray
    gcloud projects add-iam-policy-binding $ProjectId `
        --member="serviceAccount:$saEmail" `
        --role=$role `
        --condition=None `
        --quiet | Out-Null
}

# 4. Firewall Rule
Write-Host "`n[4/6] Configuring VPC Firewall Rule for Port 8088..." -ForegroundColor Yellow
$fwRule = "allow-desi-gateway-8088"
$existingFw = gcloud compute firewall-rules list --filter="name=$fwRule" --format="value(name)" --project $ProjectId 2>$null

if (-not $existingFw) {
    Write-Host "  Creating firewall rule '$fwRule'..." -ForegroundColor Gray
    gcloud compute firewall-rules create $fwRule `
        --allow=tcp:8088,tcp:80,tcp:443 `
        --target-tags="desi-gateway" `
        --description="Allow inbound HTTP traffic to Desi Language AI Gateway" `
        --project $ProjectId
} else {
    Write-Host "  Firewall rule '$fwRule' already exists." -ForegroundColor Gray
}

# 5. Provision Compute Engine VM
Write-Host "`n[5/6] Provisioning Compute Engine VM Instance..." -ForegroundColor Yellow
$existingVm = gcloud compute instances list --filter="name=$InstanceName AND zone:($Zone)" --format="value(name)" --project $ProjectId 2>$null

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$startupScriptPath = Join-Path $scriptDir "startup.sh"

if (-not $existingVm) {
    Write-Host "  Deploying VM '$InstanceName' with attached Service Account..." -ForegroundColor Gray
    gcloud compute instances create $InstanceName `
        --project=$ProjectId `
        --zone=$Zone `
        --machine-type=$MachineType `
        --image-family=ubuntu-2204-lts `
        --image-project=ubuntu-os-cloud `
        --boot-disk-size=50GB `
        --boot-disk-type=pd-balanced `
        --tags=desi-gateway,http-server,https-server `
        --service-account=$saEmail `
        --scopes=cloud-platform `
        --metadata-from-file=startup-script=$startupScriptPath
} else {
    Write-Host "  Instance '$InstanceName' already exists in $Zone." -ForegroundColor Gray
}

# 6. Retrieve Public IP & Display Access Info
Write-Host "`n[6/6] Verifying Deployment Status..." -ForegroundColor Yellow
Start-Sleep -Seconds 5
$publicIp = gcloud compute instances describe $InstanceName `
    --zone=$Zone `
    --project=$ProjectId `
    --format="value(networkInterfaces[0].accessConfigs[0].natIP)"

Write-Host "`n==================================================================" -ForegroundColor Green
Write-Host "             Deployment Successfully Initiated!                   " -ForegroundColor Green
Write-Host "==================================================================" -ForegroundColor Green
Write-Host "Instance Name:    $InstanceName"
Write-Host "Zone:             $Zone"
Write-Host "Service Account:  $saEmail"
Write-Host "Public IP:        $publicIp"
Write-Host "Desi Gateway URL: http://${publicIp}:8088"
Write-Host "Swagger / Docs:   http://${publicIp}:8088/docs"
Write-Host "`nTo test the API from PowerShell once the VM completes startup:" -ForegroundColor Cyan
Write-Host "  Invoke-RestMethod -Uri `"http://${publicIp}:8088/v2/desi/languages`"" -ForegroundColor White
Write-Host "==================================================================" -ForegroundColor Green
