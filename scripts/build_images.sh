#!/bin/bash
set -e

# Build script for all Docker images
# Usage: ./scripts/build_images.sh [service|all] [--push] [--tag TAG]
# Examples:
#   ./scripts/build_images.sh all              # Build all images locally
#   ./scripts/build_images.sh streamlit        # Build only streamlit image
#   ./scripts/build_images.sh all --push       # Build and push all images to GCR
#   ./scripts/build_images.sh api --tag v1.0.0 # Build with specific tag

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
SERVICE=${1:-all}
PUSH=${2:-""}
TAG=${3:-"latest"}
TIMESTAMP=$(date +%Y%m%d-%H%M%S)

# Load environment variables from .env if it exists
if [ -f .env ]; then
    echo "📋 Loading environment variables from .env file..."
    export $(grep -v '^#' .env | grep -v '^$' | xargs)
else
    echo "⚠️  Warning: .env file not found. Using environment variables from shell."
fi

# Validate required variables for GCP
if [ "$PUSH" == "--push" ] || [ "$PUSH" == "-p" ]; then
    if [ -z "$PROJECT_ID" ]; then
        echo -e "${RED}❌ Error: PROJECT_ID is not set${NC}"
        echo "   Set PROJECT_ID environment variable or add it to .env file"
        exit 1
    fi
    
    if ! command -v gcloud &> /dev/null; then
        echo -e "${RED}❌ Error: gcloud CLI is not installed${NC}"
        exit 1
    fi
    
    # Verify gcloud authentication
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
        echo -e "${YELLOW}⚠️  Warning: No active gcloud authentication found${NC}"
        echo "   Run: gcloud auth login"
    fi
fi

# Image registry prefix
if [ "$PUSH" == "--push" ] || [ "$PUSH" == "-p" ]; then
    REGISTRY="gcr.io/${PROJECT_ID}"
else
    REGISTRY="project-orbit"
fi

# Function to build an image
build_image() {
    local service=$1
    local dockerfile=$2
    local image_name="${REGISTRY}/project-orbit-${service}"
    local image_tag="${image_name}:${TAG}"
    local image_tag_timestamp="${image_name}:${TAG}-${TIMESTAMP}"
    
    echo ""
    echo -e "${GREEN}🔨 Building ${service} image...${NC}"
    echo "   Dockerfile: ${dockerfile}"
    echo "   Image: ${image_tag}"
    
    # Build the image
    if docker build -f "${dockerfile}" -t "${image_tag}" -t "${image_tag_timestamp}" .; then
        echo -e "${GREEN}✅ Successfully built ${image_tag}${NC}"
        
        # Push to GCR if requested
        if [ "$PUSH" == "--push" ] || [ "$PUSH" == "-p" ]; then
            echo "📤 Pushing ${image_tag} to GCR..."
            docker push "${image_tag}"
            docker push "${image_tag_timestamp}"
            echo -e "${GREEN}✅ Successfully pushed ${image_tag}${NC}"
        fi
        
        return 0
    else
        echo -e "${RED}❌ Failed to build ${image_tag}${NC}"
        return 1
    fi
}

# Build all images
build_all() {
    echo -e "${GREEN}🚀 Building all Docker images...${NC}"
    echo "   Tag: ${TAG}"
    echo "   Push to GCR: $([ "$PUSH" == "--push" ] || [ "$PUSH" == "-p" ] && echo "Yes" || echo "No")"
    
    local failed=0
    
    # Build Streamlit
    if ! build_image "streamlit" "Dockerfile.streamlit"; then
        failed=$((failed + 1))
    fi
    
    # Build HITL Dashboard
    if ! build_image "hitl" "Dockerfile.hitl"; then
        failed=$((failed + 1))
    fi
    
    # Build FastAPI
    if ! build_image "api" "Dockerfile.api"; then
        failed=$((failed + 1))
    fi
    
    # Build MCP Server
    if ! build_image "mcp" "Dockerfile.mcp"; then
        failed=$((failed + 1))
    fi
    
    # Build Agent Service
    if ! build_image "agent" "Dockerfile.agent"; then
        failed=$((failed + 1))
    fi
    
    # Build Airflow
    if ! build_image "airflow" "Dockerfile.airflow"; then
        failed=$((failed + 1))
    fi
    
    echo ""
    if [ $failed -eq 0 ]; then
        echo -e "${GREEN}✅ All images built successfully!${NC}"
        if [ "$PUSH" == "--push" ] || [ "$PUSH" == "-p" ]; then
            echo ""
            echo "📦 Images available at:"
            echo "   ${REGISTRY}/project-orbit-streamlit:${TAG}"
            echo "   ${REGISTRY}/project-orbit-hitl:${TAG}"
            echo "   ${REGISTRY}/project-orbit-api:${TAG}"
            echo "   ${REGISTRY}/project-orbit-mcp:${TAG}"
            echo "   ${REGISTRY}/project-orbit-agent:${TAG}"
            echo "   ${REGISTRY}/project-orbit-airflow:${TAG}"
        fi
        return 0
    else
        echo -e "${RED}❌ ${failed} image(s) failed to build${NC}"
        return 1
    fi
}

# Build specific service
build_service() {
    local service=$1
    local dockerfile=""
    
    case $service in
        streamlit)
            dockerfile="Dockerfile.streamlit"
            ;;
        hitl)
            dockerfile="Dockerfile.hitl"
            ;;
        api)
            dockerfile="Dockerfile.api"
            ;;
        mcp)
            dockerfile="Dockerfile.mcp"
            ;;
        agent)
            dockerfile="Dockerfile.agent"
            ;;
        airflow)
            dockerfile="Dockerfile.airflow"
            ;;
        *)
            echo -e "${RED}❌ Unknown service: ${service}${NC}"
            echo "   Available services: streamlit, hitl, api, mcp, agent, airflow"
            exit 1
            ;;
    esac
    
    build_image "${service}" "${dockerfile}"
}

# Main execution
case $SERVICE in
    all)
        build_all
        ;;
    *)
        build_service "$SERVICE"
        ;;
esac

echo ""
echo -e "${GREEN}🎉 Build process completed!${NC}"

