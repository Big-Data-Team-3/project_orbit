#!/bin/bash
# Script to check service account permissions

set -e

PROJECT_ID="project-orbit123"
SA_EMAIL="airflow-composer-sa@project-orbit123.iam.gserviceaccount.com"

echo "=========================================="
echo "Checking Service Account Permissions"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Service Account: $SA_EMAIL"
echo ""

# Check if service account exists
echo "Checking if service account exists..."
if gcloud iam service-accounts describe "$SA_EMAIL" --project="$PROJECT_ID" > /dev/null 2>&1; then
    echo "✅ Service account exists"
else
    echo "❌ Service account not found!"
    echo ""
    echo "Creating service account..."
    gcloud iam service-accounts create airflow-composer-sa \
        --display-name="Airflow Composer Service Account" \
        --description="Service account for Cloud Composer Airflow DAGs" \
        --project="$PROJECT_ID"
    
    if [ $? -eq 0 ]; then
        echo "✅ Service account created!"
    else
        echo "❌ Failed to create service account!"
        exit 1
    fi
fi

echo ""
echo "Checking IAM roles..."

# Check required roles
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

# Check bucket access if config exists
if [ -f .gcs_config ]; then
    source .gcs_config
    if [ ! -z "$BUCKET_NAME" ]; then
        echo ""
        echo "Verifying bucket access for service account..."
        echo "Bucket: $BUCKET_NAME"
        echo "Note: Service account needs storage.admin role (checked above)"
        echo "      This grants access to all buckets in the project."
    fi
fi

echo ""
echo "=========================================="
echo "Service Account Check Complete!"
echo "=========================================="
echo ""
echo "Next Steps:"
echo "1. Run: bash scripts/install_composer_dependencies.sh"
echo "2. Run: bash scripts/set_airflow_variables.sh"
echo "3. Run: bash scripts/deploy_dags.sh"
echo "=========================================="

