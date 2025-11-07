#!/bin/bash
# Script to verify bucket connection and service account permissions

set -e

PROJECT_ID="project-orbit123"
SA_EMAIL="airflow-composer-sa@project-orbit123.iam.gserviceaccount.com"

echo "=========================================="
echo "Verifying Bucket Connection & Permissions"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Service Account: $SA_EMAIL"
echo ""

# Load bucket name from config
if [ ! -f .gcs_config ]; then
    echo "❌ ERROR: .gcs_config not found!"
    echo "Run: bash scripts/setup_gcs_buckets.sh first"
    exit 1
fi

source .gcs_config

if [ -z "$BUCKET_NAME" ]; then
    echo "❌ ERROR: BUCKET_NAME not set in .gcs_config"
    exit 1
fi

echo "Target Data Bucket: $BUCKET_NAME"
echo ""

# Step 1: Verify bucket exists and is accessible
echo "Step 1: Verifying bucket access..."
if gsutil ls "gs://${BUCKET_NAME}" > /dev/null 2>&1; then
    echo "✅ Bucket '$BUCKET_NAME' exists and is accessible"
else
    echo "❌ ERROR: Cannot access bucket '$BUCKET_NAME'"
    echo "Please verify:"
    echo "1. Bucket name is correct"
    echo "2. You have Storage Admin role"
    echo "3. Bucket exists in project $PROJECT_ID"
    exit 1
fi

# Step 2: Verify seed file exists
echo ""
echo "Step 2: Verifying seed file..."
if gsutil ls "gs://${BUCKET_NAME}/seed/forbes_ai50_seed.json" > /dev/null 2>&1; then
    echo "✅ Seed file found: gs://${BUCKET_NAME}/seed/forbes_ai50_seed.json"
else
    echo "⚠️  WARNING: Seed file not found!"
    echo "   Expected: gs://${BUCKET_NAME}/seed/forbes_ai50_seed.json"
    read -p "Upload seed file now? (y/n): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [ -f "data/forbes_ai50_seed.json" ]; then
            gsutil cp "data/forbes_ai50_seed.json" "gs://${BUCKET_NAME}/seed/forbes_ai50_seed.json"
            echo "✅ Seed file uploaded"
        else
            echo "❌ Local seed file not found at data/forbes_ai50_seed.json"
        fi
    fi
fi

# Step 3: Check service account exists
echo ""
echo "Step 3: Checking service account..."
if gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID" > /dev/null 2>&1; then
    echo "✅ Service account exists"
else
    echo "❌ Service account not found!"
    echo "Creating service account..."
    gcloud iam service-accounts create airflow-composer-sa \
        --display-name="Airflow Composer Service Account" \
        --description="Service account for Cloud Composer Airflow DAGs" \
        --project="$PROJECT_ID"
    
    if [ $? -eq 0 ]; then
        echo "✅ Service account created"
    else
        echo "❌ Failed to create service account"
        exit 1
    fi
fi

# Step 4: Verify service account permissions
echo ""
echo "Step 4: Verifying service account permissions..."

REQUIRED_ROLES=(
    "roles/composer.worker"
    "roles/storage.admin"
    "roles/iam.serviceAccountUser"
)

MISSING_ROLES=()

for ROLE in "${REQUIRED_ROLES[@]}"; do
    echo -n "Checking $ROLE... "
    if gcloud projects get-iam-policy "$PROJECT_ID" \
        --flatten="bindings[].members" \
        --filter="bindings.members=serviceAccount:$SA_EMAIL AND bindings.role=$ROLE" \
        --format="get(bindings.role)" | grep -q "$ROLE" 2>/dev/null; then
        echo "✅ Granted"
    else
        echo "❌ Missing"
        MISSING_ROLES+=("$ROLE")
    fi
done

# Grant missing roles
if [ ${#MISSING_ROLES[@]} -gt 0 ]; then
    echo ""
    echo "Granting missing roles..."
    
    for ROLE in "${MISSING_ROLES[@]}"; do
        echo "Granting $ROLE..."
        gcloud projects add-iam-policy-binding "$PROJECT_ID" \
            --member="serviceAccount:$SA_EMAIL" \
            --role="$ROLE" \
            --condition=None
        
        if [ $? -eq 0 ]; then
            echo "  ✅ Granted $ROLE"
        else
            echo "  ❌ Failed to grant $ROLE"
        fi
    done
else
    echo ""
    echo "✅ All required roles are granted!"
fi

# Step 5: Verify bucket permissions for service account
echo ""
echo "Step 5: Verifying bucket permissions for service account..."
echo "Testing service account access to bucket..."

# Try to list bucket contents as service account (indirect test)
BUCKET_ACCESS_OK=true

# Check if service account can access bucket
# Note: We can't directly test as service account, but we verify roles are set
if [[ " ${MISSING_ROLES[@]} " =~ " roles/storage.admin " ]]; then
    echo "⚠️  WARNING: storage.admin role was just granted. Changes may take a few minutes to propagate."
    BUCKET_ACCESS_OK=false
else
    echo "✅ Service account has storage.admin role on project"
    echo "   This grants access to all buckets in the project, including $BUCKET_NAME"
fi

# Step 6: Summary
echo ""
echo "=========================================="
echo "Verification Summary"
echo "=========================================="
echo "✅ Bucket: $BUCKET_NAME"
echo "✅ Service Account: $SA_EMAIL"
if [ ${#MISSING_ROLES[@]} -eq 0 ]; then
    echo "✅ All IAM roles granted"
else
    echo "⚠️  Some roles were just granted (may take a few minutes to propagate)"
fi
echo ""
echo "Next Steps:"
echo "1. Run: bash scripts/install_composer_dependencies.sh"
echo "2. Run: bash scripts/set_airflow_variables.sh"
echo "3. Run: bash scripts/deploy_dags.sh"
echo ""
echo "To verify bucket access after DAG runs, check:"
echo "  gsutil ls gs://${BUCKET_NAME}/raw/"
echo "=========================================="
