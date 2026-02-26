#!/bin/bash
set -euo pipefail

# =============================================================================
# Bybit MCP - Google Cloud Setup Script
# Run this once to configure GCP project, secrets, and Artifact Registry
# =============================================================================

PROJECT_ID="${1:-bybit-mcp-trading}"
REGION="us-east1"
SERVICE_ACCOUNT_NAME="bybit-mcp-deployer"

echo "=== Setting up GCP project: ${PROJECT_ID} ==="

# 1. Create project (ignore if exists)
echo "Creating project..."
gcloud projects create "${PROJECT_ID}" --name="Bybit MCP Trading" 2>/dev/null || echo "Project already exists"

# 2. Set project
gcloud config set project "${PROJECT_ID}"

# 3. Link billing (user must do this manually if needed)
echo ""
echo "IMPORTANT: Ensure billing is enabled for project ${PROJECT_ID}"
echo "Visit: https://console.cloud.google.com/billing/linkedaccount?project=${PROJECT_ID}"
echo ""
read -p "Press Enter once billing is enabled..."

# 4. Enable required APIs
echo "Enabling APIs..."
gcloud services enable \
    run.googleapis.com \
    artifactregistry.googleapis.com \
    secretmanager.googleapis.com \
    cloudbuild.googleapis.com \
    --project="${PROJECT_ID}"

# 5. Create Artifact Registry repository
echo "Creating Artifact Registry repo..."
gcloud artifacts repositories create bybit-mcp \
    --repository-format=docker \
    --location="${REGION}" \
    --description="Bybit MCP Docker images" \
    --project="${PROJECT_ID}" 2>/dev/null || echo "Registry already exists"

# 6. Create service account for GitHub Actions
echo "Creating service account..."
gcloud iam service-accounts create "${SERVICE_ACCOUNT_NAME}" \
    --display-name="Bybit MCP Deployer" \
    --project="${PROJECT_ID}" 2>/dev/null || echo "Service account already exists"

SA_EMAIL="${SERVICE_ACCOUNT_NAME}@${PROJECT_ID}.iam.gserviceaccount.com"

# 7. Grant roles
echo "Granting IAM roles..."
for ROLE in \
    roles/run.admin \
    roles/artifactregistry.writer \
    roles/secretmanager.secretAccessor \
    roles/iam.serviceAccountUser; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="${ROLE}" \
        --quiet
done

# 8. Create service account key for GitHub Actions
echo "Creating service account key..."
KEY_FILE="/tmp/gcp-sa-key-${PROJECT_ID}.json"
gcloud iam service-accounts keys create "${KEY_FILE}" \
    --iam-account="${SA_EMAIL}" \
    --project="${PROJECT_ID}"

echo ""
echo "=== Creating Secret Manager secrets ==="

# 9. Create secrets (empty - user fills in later)
for SECRET in bybit-api-key bybit-api-secret mcp-auth-token; do
    echo "Creating secret: ${SECRET}"
    printf "" | gcloud secrets create "${SECRET}" \
        --data-file=- \
        --replication-policy=automatic \
        --project="${PROJECT_ID}" 2>/dev/null || echo "Secret ${SECRET} already exists"
done

echo ""
echo "========================================="
echo "SETUP COMPLETE!"
echo "========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Set your secrets in GCP Secret Manager:"
echo "   echo -n 'YOUR_BYBIT_API_KEY' | gcloud secrets versions add bybit-api-key --data-file=- --project=${PROJECT_ID}"
echo "   echo -n 'YOUR_BYBIT_API_SECRET' | gcloud secrets versions add bybit-api-secret --data-file=- --project=${PROJECT_ID}"
echo "   echo -n 'YOUR_MCP_AUTH_TOKEN' | gcloud secrets versions add mcp-auth-token --data-file=- --project=${PROJECT_ID}"
echo ""
echo "2. Add GitHub repo secrets:"
echo "   gh secret set GCP_PROJECT_ID --body '${PROJECT_ID}'"
echo "   gh secret set GCP_SA_KEY < '${KEY_FILE}'"
echo ""
echo "3. Push to main to trigger deploy:"
echo "   git push origin main"
echo ""
echo "Service account key saved to: ${KEY_FILE}"
echo "DELETE this file after adding it to GitHub secrets!"
