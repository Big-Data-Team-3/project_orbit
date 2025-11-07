#!/bin/bash
# Script to run structured_extraction function in batches of 3 companies

set -e

PROJECT_ID="project-orbit123"
REGION="us-central1"
BATCH_SIZE=3

# Get script and project directories
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "=========================================="
echo "Batch Structured Extraction Execution"
echo "=========================================="
echo "Project: $PROJECT_ID"
echo "Region: $REGION"
echo "Batch Size: $BATCH_SIZE companies per batch"
echo ""

# Load function URL
if [ ! -f "$PROJECT_ROOT/.functions_config" ]; then
    echo "❌ ERROR: .functions_config not found!"
    echo "Run: bash scripts/deploy_functions.sh first"
    exit 1
fi

source "$PROJECT_ROOT/.functions_config"

if [ -z "$STRUCTURED_EXTRACTION_URL" ]; then
    echo "❌ ERROR: STRUCTURED_EXTRACTION_URL not found in config"
    echo "Run: bash scripts/deploy_functions.sh first"
    exit 1
fi

echo "Function URL: $STRUCTURED_EXTRACTION_URL"
echo ""

# Get total number of companies from GCS seed file
echo "Loading company list from GCS..."
if [ -z "$BUCKET_NAME" ]; then
    echo "❌ ERROR: BUCKET_NAME not found in config"
    exit 1
fi

# Download seed file temporarily to count companies
TEMP_SEED=$(mktemp)
gsutil cp "gs://${BUCKET_NAME}/seed/forbes_ai50_seed.json" "$TEMP_SEED" 2>/dev/null || {
    echo "❌ ERROR: Failed to download seed file from gs://${BUCKET_NAME}/seed/forbes_ai50_seed.json"
    exit 1
}

# Count companies using Python
TOTAL_COMPANIES=$(python3 -c "import json; print(len(json.load(open('$TEMP_SEED'))))" 2>/dev/null || echo "50")
rm "$TEMP_SEED"

if [ -z "$TOTAL_COMPANIES" ] || [ "$TOTAL_COMPANIES" -eq 0 ]; then
    echo "⚠️  WARNING: Could not determine total companies, defaulting to 50"
    TOTAL_COMPANIES=50
fi

echo "Total companies: $TOTAL_COMPANIES"
NUM_BATCHES=$(( ($TOTAL_COMPANIES + $BATCH_SIZE - 1) / $BATCH_SIZE ))  # Ceiling division
echo "Number of batches: $NUM_BATCHES"
echo ""

read -p "Continue with batch processing? (y/n): " -n 1 -r
echo
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "Cancelled."
    exit 0
fi

echo ""
echo "=========================================="
echo "Starting Batch Processing"
echo "=========================================="
echo ""

# Track results
SUCCESSFUL_BATCHES=0
FAILED_BATCHES=0
BATCH_RESULTS=()

# Process each batch
for ((batch=0; batch<$NUM_BATCHES; batch++)); do
    start=$((batch * BATCH_SIZE))
    end=$((start + BATCH_SIZE))
    
    # Adjust end if it exceeds total companies
    if [ $end -gt $TOTAL_COMPANIES ]; then
        end=$TOTAL_COMPANIES
    fi
    
    batch_num=$((batch + 1))
    
    echo "----------------------------------------"
    echo "Batch $batch_num/$NUM_BATCHES: Companies $start to $((end-1))"
    echo "----------------------------------------"
    
    # Trigger function with batch parameters
    response=$(curl -s -w "\n%{http_code}" -X POST \
        "${STRUCTURED_EXTRACTION_URL}?start=${start}&end=${end}&batch_size=${BATCH_SIZE}" \
        --max-time 600)
    
    http_code=$(echo "$response" | tail -n1)
    response_body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" = "200" ]; then
        echo "✅ Batch $batch_num completed successfully"
        echo "$response_body" | python3 -m json.tool 2>/dev/null || echo "$response_body"
        SUCCESSFUL_BATCHES=$((SUCCESSFUL_BATCHES + 1))
        BATCH_RESULTS+=("Batch $batch_num: SUCCESS")
    else
        echo "❌ Batch $batch_num failed (HTTP $http_code)"
        echo "Response: $response_body"
        FAILED_BATCHES=$((FAILED_BATCHES + 1))
        BATCH_RESULTS+=("Batch $batch_num: FAILED (HTTP $http_code)")
        
        # Ask if user wants to continue
        read -p "Continue with next batch? (y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            echo "Stopped by user."
            break
        fi
    fi
    
    echo ""
    
    # Small delay between batches to avoid rate limiting
    if [ $batch -lt $((NUM_BATCHES - 1)) ]; then
        echo "Waiting 5 seconds before next batch..."
        sleep 5
    fi
done

echo ""
echo "=========================================="
echo "Batch Processing Complete!"
echo "=========================================="
echo ""
echo "Summary:"
echo "  Total batches: $NUM_BATCHES"
echo "  Successful: $SUCCESSFUL_BATCHES"
echo "  Failed: $FAILED_BATCHES"
echo ""
echo "Batch Results:"
for result in "${BATCH_RESULTS[@]}"; do
    echo "  $result"
done
echo ""
echo "Results saved in GCS:"
echo "  gs://${BUCKET_NAME}/scraping_results/structured_extraction_results_batch_*.json"
echo "  gs://${BUCKET_NAME}/structured/*.json"
echo "  gs://${BUCKET_NAME}/payloads/*.json"
echo ""
echo "View all results:"
echo "  gsutil ls gs://${BUCKET_NAME}/structured/"
echo "  gsutil ls gs://${BUCKET_NAME}/payloads/"
echo "=========================================="

