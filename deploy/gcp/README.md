# Google Cloud Compute Engine Deployment for Desi Language AI

This directory provides automated scripts to provision and deploy the **Desi Language AI Platform** on Google Cloud Compute Engine using official **Application Default Credentials (ADC)** and dedicated Service Accounts.

---

## Architecture & Authentication Flow

```
[Local Admin / CI/CD]
      │
      ▼  (gcloud auth / user credentials)
gcloud CLI creates:
      ├── 1. Service Account: `desi-engine-sa@PROJECT_ID.iam.gserviceaccount.com`
      ├── 2. IAM Roles: Logging Writer, Monitoring Metric Writer, Storage Object Viewer
      ├── 3. VPC Firewall Rule: `allow-desi-gateway-8088`
      └── 4. Compute Engine Instance: `desi-ai-instance` (Ubuntu 22.04 LTS)
                  │
                  ▼ (Attached Service Account - Zero Keys on Disk)
            Compute Engine VM
                  │  (Metadata Server: http://metadata.google.internal)
                  ▼
            Desi Language AI Gateway (Docker Compose on Port 8088)
```

### Why This Follows Security Best Practices:
1. **Zero Hardcoded Secrets**: No service account `.json` private keys are stored on the VM disk or in git.
2. **Ambient ADC Authentication**: The instance metadata server automatically issues short-lived OAuth 2.0 access tokens to code running inside the instance.
3. **Least Privilege**: Only the exact logging, monitoring, and storage roles required are granted.

---

## Deployment Instructions

### Prerequisites
1. [Google Cloud CLI (`gcloud`) installed](https://cloud.google.com/sdk/docs/install).
2. Authenticated with Google Cloud:
   ```bash
   gcloud auth login
   gcloud config set project YOUR_PROJECT_ID
   ```

---

### Option A: Deploying from Windows (PowerShell)

Run [`deploy_compute_engine.ps1`](./deploy_compute_engine.ps1):

```powershell
# Deploy with default parameters (Asia South / Mumbai zone)
.\deploy\gcp\deploy_compute_engine.ps1 -ProjectId "YOUR_GCP_PROJECT_ID"

# Or customize zone and machine type
.\deploy\gcp\deploy_compute_engine.ps1 `
    -ProjectId "YOUR_GCP_PROJECT_ID" `
    -Zone "asia-south1-a" `
    -MachineType "e2-standard-4"
```

---

### Option B: Deploying from Linux / macOS / Cloud Shell (Bash)

Make executable and run [`deploy_compute_engine.sh`](./deploy_compute_engine.sh):

```bash
chmod +x ./deploy/gcp/deploy_compute_engine.sh
./deploy/gcp/deploy_compute_engine.sh YOUR_GCP_PROJECT_ID asia-south1-a desi-ai-instance e2-standard-4
```

---

## Verifying Deployment

Once the VM boots and executes [`startup.sh`](./startup.sh) (takes ~1-2 minutes):

1. **Check Health & Desi Languages**:
   ```bash
   curl -X GET "http://<VM_PUBLIC_IP>:8088/v2/desi/languages"
   ```

2. **Test Indic Translation (Hindi with Formal Register)**:
   ```bash
   curl -X POST "http://<VM_PUBLIC_IP>:8088/v2/desi/translate" \
        -H "Content-Type: application/json" \
        -d '{
          "text": ["Welcome to Desi AI"],
          "target_lang": "hi",
          "honorific": "formal",
          "respectful_suffix": true
        }'
   ```

3. **SSH into the VM if needed**:
   ```bash
   gcloud compute ssh desi-ai-instance --zone=asia-south1-a
   ```
