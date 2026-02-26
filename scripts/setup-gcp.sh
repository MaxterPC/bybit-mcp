#!/bin/bash
set -euo pipefail

# =============================================================================
# Bybit MCP - Google Cloud Setup Script
# Run this once to configure GCP project, secrets, Artifact Registry, and
# Workload Identity Federation for GitHub Actions.
# =============================================================================

PROJECT_ID="${1:-bybit-mcp-trading}"
GITHUB_REPO="${2:-}"  # e.g. "MaxterPC/bybit-mcp"
REGION="us-east1"
SERVICE_ACCOUNT_NAME="bybit-mcp-deployer"
WIF_POOL="github-pool"
WIF_PROVIDER="github-provider"

if [ -z "${GITHUB_REPO}" ]; then
    echo "Usage: $0 <PROJECT_ID> <GITHUB_OWNER/REPO>"
    echo "Example: $0 bybit-mcp-trading MaxterPC/bybit-mcp"
    exit 1
fi

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
    iamcredentials.googleapis.com \
    iam.googleapis.com \
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
PROJECT_NUMBER=$(gcloud projects describe "${PROJECT_ID}" --format='value(projectNumber)')

# 7. Grant project-level roles (non-secret roles only)
echo "Granting IAM roles..."
for ROLE in \
    roles/run.admin \
    roles/artifactregistry.writer \
    roles/iam.serviceAccountUser; do
    gcloud projects add-iam-policy-binding "${PROJECT_ID}" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="${ROLE}" \
        --quiet
done

# 8. Create secrets and grant per-secret access
echo ""
echo "=== Creating Secret Manager secrets ==="

SECRETS=(bybit-api-key bybit-api-secret oauth-secret mcp-api-key registration-token)

for SECRET in "${SECRETS[@]}"; do
    echo "Creating secret: ${SECRET}"
    printf "" | gcloud secrets create "${SECRET}" \
        --data-file=- \
        --replication-policy=automatic \
        --project="${PROJECT_ID}" 2>/dev/null || echo "Secret ${SECRET} already exists"

    # Grant per-secret accessor role (not project-wide)
    gcloud secrets add-iam-policy-binding "${SECRET}" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="roles/secretmanager.secretAccessor" \
        --project="${PROJECT_ID}" \
        --quiet
done

# Also grant secretVersionAdder for deploy-time secret updates
for SECRET in "${SECRETS[@]}"; do
    gcloud secrets add-iam-policy-binding "${SECRET}" \
        --member="serviceAccount:${SA_EMAIL}" \
        --role="roles/secretmanager.secretVersionManager" \
        --project="${PROJECT_ID}" \
        --quiet
done

# 9. Set up Workload Identity Federation for GitHub Actions
echo ""
echo "=== Setting up Workload Identity Federation ==="

# Create Workload Identity Pool
gcloud iam workload-identity-pools create "${WIF_POOL}" \
    --location="global" \
    --display-name="GitHub Actions Pool" \
    --project="${PROJECT_ID}" 2>/dev/null || echo "WIF pool already exists"

# Create OIDC provider for GitHub
gcloud iam workload-identity-pools providers create-oidc "${WIF_PROVIDER}" \
    --location="global" \
    --workload-identity-pool="${WIF_POOL}" \
    --issuer-uri="https://token.actions.githubusercontent.com" \
    --attribute-mapping="google.subject=assertion.sub,attribute.repository=assertion.repository" \
    --attribute-condition="assertion.repository=='${GITHUB_REPO}'" \
    --project="${PROJECT_ID}" 2>/dev/null || echo "WIF provider already exists"

# Allow GitHub Actions to impersonate the service account
gcloud iam service-accounts add-iam-policy-binding "${SA_EMAIL}" \
    --role="roles/iam.workloadIdentityUser" \
    --member="principalSet://iam.googleapis.com/projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/attribute.repository/${GITHUB_REPO}" \
    --project="${PROJECT_ID}" \
    --quiet

WIF_PROVIDER_FULL="projects/${PROJECT_NUMBER}/locations/global/workloadIdentityPools/${WIF_POOL}/providers/${WIF_PROVIDER}"

echo ""
echo "========================================="
echo "SETUP COMPLETE!"
echo "========================================="
echo ""
echo "Next steps:"
echo ""
echo "1. Set your secrets in GCP Secret Manager:"
echo "   echo -n 'VALUE' | gcloud secrets versions add bybit-api-key --data-file=- --project=${PROJECT_ID}"
echo "   echo -n 'VALUE' | gcloud secrets versions add bybit-api-secret --data-file=- --project=${PROJECT_ID}"
echo "   echo -n 'VALUE' | gcloud secrets versions add oauth-secret --data-file=- --project=${PROJECT_ID}"
echo "   echo -n 'VALUE' | gcloud secrets versions add mcp-api-key --data-file=- --project=${PROJECT_ID}"
echo "   echo -n 'VALUE' | gcloud secrets versions add registration-token --data-file=- --project=${PROJECT_ID}"
echo ""
echo "2. Add GitHub repo secrets (Workload Identity Federation - no key file needed):"
echo "   gh secret set GCP_PROJECT_ID --body '${PROJECT_ID}'"
echo "   gh secret set GCP_WIF_PROVIDER --body '${WIF_PROVIDER_FULL}'"
echo "   gh secret set GCP_SA_EMAIL --body '${SA_EMAIL}'"
echo ""
echo "3. Push to main to trigger deploy:"
echo "   git push origin main"
echo ""
echo "No service account key files needed - WIF handles authentication securely!"
