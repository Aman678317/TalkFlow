#!/usr/bin/env bash
# ==============================================================================
# Desi / GlobalTalk AI — Compute Engine VM Startup Script
# Automatically executes on VM boot to bootstrap Docker and launch the stack.
# Uses Google Cloud Application Default Credentials (ADC) from the attached SA.
# ==============================================================================

set -euo pipefail

echo "==> [1/5] Updating system packages and installing prerequisites..."
apt-get update -y
apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    jq

echo "==> [2/5] Installing Docker Engine..."
mkdir -p /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg --yes

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(lsb_release -cs) stable" | tee /etc/apt/sources.list.d/docker.list > /dev/null

apt-get update -y
apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin

systemctl enable docker
systemctl start docker

echo "==> [3/5] Querying Compute Engine Instance Metadata..."
VM_ZONE=$(curl -s -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/zone" | awk -F'/' '{print $NF}')
VM_NAME=$(curl -s -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/name")
SA_EMAIL=$(curl -s -H "Metadata-Flavor: Google" "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/email")

echo "Running on instance: ${VM_NAME} in zone: ${VM_ZONE}"
echo "Authenticated via Service Account: ${SA_EMAIL}"

echo "==> [4/5] Preparing application directory..."
APP_DIR="/opt/desi-ai"
mkdir -p "${APP_DIR}"
cd "${APP_DIR}"

# Write standalone production docker-compose for the API gateway
cat << 'EOF' > docker-compose.prod.yml
version: '3.8'

services:
  postgres:
    image: postgres:16-alpine
    restart: always
    environment:
      POSTGRES_USER: globaltalk
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:-desi_prod_secure_pass}
      POSTGRES_DB: globaltalk
    volumes:
      - pgdata:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U globaltalk"]
      interval: 5s
      timeout: 3s
      retries: 5

  redis:
    image: redis:7-alpine
    restart: always
    volumes:
      - redisdata:/data
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5

  desi-api:
    image: python:3.11-slim
    restart: always
    working_dir: /app
    volumes:
      - /opt/desi-ai/app:/app
    environment:
      APP_ENV: production
      DATABASE_URL: postgresql+asyncpg://globaltalk:${POSTGRES_PASSWORD:-desi_prod_secure_pass}@postgres:5432/globaltalk
      REDIS_URL: redis://redis:6379/0
      PORT: 8088
      DESI_SERVER_URL: http://0.0.0.0:8088
    ports:
      - "8088:8088"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    command: >
      bash -c "pip install --no-cache-dir fastapi uvicorn sqlalchemy asyncpg pydantic redis httpx python-multipart &&
               uvicorn app.main:app --host 0.0.0.0 --port 8088 --workers 4"

volumes:
  pgdata:
  redisdata:
EOF

echo "==> [5/5] Launching Desi Language AI Stack..."
docker compose -f docker-compose.prod.yml up -d

echo "==> Desi AI Compute Engine VM Initialization Complete!"
EOF
