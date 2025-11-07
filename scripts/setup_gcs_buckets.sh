#!/bin/bash
# Script to verify existing GCS bucket or create new one and upload seed data

set -e

PROJECT_ID="project-orbit123"
LOCATION="us-central1"

echo "=========================================="
echo "Setting up GCS Buckets"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Location: $LOCATION"
echo ""

# Check if bucket already exists in config
BUCKET_NAME=""
if [ -f .gcs_config ]; then
    source .gcs_config
    if [ ! -z "$BUCKET_NAME" ]; then
        echo "Found existing bucket config: $BUCKET_NAME"
        read -p "Use this bucket? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            BUCKET_NAME=""
        fi
    fi
fi

# Prompt user for bucket choice
if [ -z "$BUCKET_NAME" ]; then
    echo "Do you want to use an existing GCS bucket?"
    echo "  (Note: Cloud Composer creates its own bucket for DAGs/plugins)"
    echo "  (This is for your DATA bucket where scraped data will be stored)"
    echo ""
    read -p "Use existing bucket? (y/n): " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        read -p "Enter the name of your existing GCS bucket (e.g., project-orbit-data-12345): " USER_BUCKET_NAME
        USER_BUCKET_NAME=$(echo "$USER_BUCKET_NAME" | tr -d ' ')  # Remove spaces
        
        if [ -z "$USER_BUCKET_NAME" ]; then
            echo "❌ ERROR: Bucket name cannot be empty."
            exit 1
        fi
        
        echo ""
        echo "Checking if bucket '$USER_BUCKET_NAME' exists and is accessible..."
        
        # Check if bucket exists and is accessible
        if ! gsutil ls "gs://${USER_BUCKET_NAME}" > /dev/null 2>&1; then
            echo "❌ ERROR: Bucket '$USER_BUCKET_NAME' not found or you don't have permissions."
            echo ""
            echo "Please verify:"
            echo "1. Bucket name is correct: $USER_BUCKET_NAME"
            echo "2. You have 'Storage Admin' or 'Storage Object Admin' role on this bucket"
            echo "3. Bucket exists in project: $PROJECT_ID"
            echo ""
            echo "To list your buckets, run:"
            echo "  gsutil ls -p $PROJECT_ID"
            exit 1
        fi
        
        BUCKET_NAME="$USER_BUCKET_NAME"
        echo "✅ Bucket '$BUCKET_NAME' exists and is accessible!"
        echo ""
        
        # Verify bucket structure
        echo "Verifying bucket structure..."
        REQUIRED_FOLDERS=("raw/" "structured/" "payloads/" "scraping_results/" "seed/")
        SEED_FILE="seed/forbes_ai50_seed.json"
        MISSING_ITEMS=()
        
        # Check seed file
        if ! gsutil ls "gs://${BUCKET_NAME}/${SEED_FILE}" > /dev/null 2>&1; then
            MISSING_ITEMS+=("$SEED_FILE")
            echo "⚠️  Warning: Seed file 'gs://${BUCKET_NAME}/${SEED_FILE}' not found."
        else
            echo "✅ Seed file found: gs://${BUCKET_NAME}/${SEED_FILE}"
        fi
        
        # Check folders
        for FOLDER in "${REQUIRED_FOLDERS[@]}"; do
            if ! gsutil ls "gs://${BUCKET_NAME}/${FOLDER}" > /dev/null 2>&1; then
                MISSING_ITEMS+=("$FOLDER")
                echo "⚠️  Warning: Folder 'gs://${BUCKET_NAME}/${FOLDER}' not found."
            else
                echo "✅ Folder found: gs://${BUCKET_NAME}/${FOLDER}"
            fi
        done
        
        # Handle missing items
        if [ ${#MISSING_ITEMS[@]} -gt 0 ]; then
            echo ""
            echo "Missing items detected. Would you like to create/upload them?"
            read -p "Create missing folders and upload seed file? (y/n): " -n 1 -r
            echo
            
            if [[ $REPLY =~ ^[Yy]$ ]]; then
                # Create missing folders
                for ITEM in "${MISSING_ITEMS[@]}"; do
                    if [[ "$ITEM" == */ ]]; then
                        # It's a folder
                        echo "Creating folder: gs://${BUCKET_NAME}/${ITEM}"
                        gsutil -m mkdir "gs://${BUCKET_NAME}/${ITEM}" 2>/dev/null || true
                        echo "  ✅ Created"
                    else
                        # It's the seed file
                        if [ -f "data/forbes_ai50_seed.json" ]; then
                            echo "Uploading seed file: gs://${BUCKET_NAME}/${ITEM}"
                            gsutil cp "data/forbes_ai50_seed.json" "gs://${BUCKET_NAME}/${ITEM}"
                            echo "  ✅ Uploaded"
                        else
                            echo "  ⚠️  Local seed file 'data/forbes_ai50_seed.json' not found."
                            echo "     Please ensure seed file exists in GCS manually."
                        fi
                    fi
                done
            else
                echo "Skipping. Please ensure all required items exist in the bucket."
            fi
        fi
        
        echo ""
        echo "✅ Bucket verification complete!"
        
    else
        # Create a new bucket
        TIMESTAMP=$(date +%s)
        BUCKET_NAME="project-orbit-data-${TIMESTAMP}"
        
        echo "Creating new GCS bucket: $BUCKET_NAME"
        if ! gsutil mb -p "$PROJECT_ID" -l "$LOCATION" "gs://${BUCKET_NAME}" 2>/dev/null; then
            echo "❌ Failed to create bucket. It may already exist or name is not unique."
            echo "Please choose a different bucket name or use an existing bucket."
            exit 1
        fi
        
        echo "✅ Bucket created successfully!"
        echo ""
        
        echo "Creating folder structure..."
        gsutil -m mkdir "gs://${BUCKET_NAME}/seed/" 2>/dev/null || true
        gsutil -m mkdir "gs://${BUCKET_NAME}/raw/" 2>/dev/null || true
        gsutil -m mkdir "gs://${BUCKET_NAME}/structured/" 2>/dev/null || true
        gsutil -m mkdir "gs://${BUCKET_NAME}/payloads/" 2>/dev/null || true
        gsutil -m mkdir "gs://${BUCKET_NAME}/scraping_results/" 2>/dev/null || true
        echo "✅ Folder structure created!"
        echo ""
        
        echo "Uploading seed file..."
        if [ -f "data/forbes_ai50_seed.json" ]; then
            gsutil cp "data/forbes_ai50_seed.json" "gs://${BUCKET_NAME}/seed/forbes_ai50_seed.json"
            echo "✅ Seed file uploaded!"
        else
            echo "⚠️  WARNING: Local seed file 'data/forbes_ai50_seed.json' not found!"
            echo "   Please upload it manually later:"
            echo "   gsutil cp data/forbes_ai50_seed.json gs://${BUCKET_NAME}/seed/"
        fi
    fi
fi

# Final verification
echo ""
echo "=========================================="
echo "Final Verification"
echo "=========================================="
echo "Listing bucket contents..."
gsutil ls -r "gs://${BUCKET_NAME}/" | head -20
echo ""

# Save bucket configuration
echo "Saving bucket configuration..."
cat > .gcs_config << EOF
# GCS Configuration
# Generated on $(date)

PROJECT_ID=$PROJECT_ID
LOCATION=$LOCATION
BUCKET_NAME=$BUCKET_NAME
SEED_FILE_PATH=gs://$BUCKET_NAME/seed/forbes_ai50_seed.json
RAW_DATA_PATH=gs://$BUCKET_NAME/raw/
STRUCTURED_DATA_PATH=gs://$BUCKET_NAME/structured/
PAYLOADS_PATH=gs://$BUCKET_NAME/payloads/
RESULTS_PATH=gs://$BUCKET_NAME/scraping_results/
EOF

echo "✅ Configuration saved to .gcs_config"
echo ""
echo "=========================================="
echo "GCS Setup Complete!"
echo "=========================================="
echo "Data Bucket: $BUCKET_NAME"
echo ""
echo "Note: Cloud Composer uses a separate bucket for DAGs/plugins."
echo "Your data will be stored in: gs://$BUCKET_NAME/"
echo ""
echo "Next Steps:"
echo "1. Run: bash scripts/check_service_account.sh"
echo "2. Ensure service account has access to this bucket"
echo "=========================================="

