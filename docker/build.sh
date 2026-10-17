#!/bin/bash
# UCM Docker Build Script
# Builds and optionally pushes Docker images

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# Configuration
IMAGE_NAME="${IMAGE_NAME:-ucm}"
IMAGE_TAG="${IMAGE_TAG:-latest}"
VERSION="${VERSION:-1.0.0}"
REGISTRY="${REGISTRY:-}"  # e.g., docker.io/username or ghcr.io/username
PLATFORMS="${PLATFORMS:-linux/amd64,linux/arm64}"

echo -e "${BLUE}╔════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║  UCM Docker Build Script              ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════╝${NC}"
echo ""

# Check if Docker is installed
if ! command -v docker &> /dev/null; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    exit 1
fi

echo -e "${GREEN}✅ Docker found: $(docker --version)${NC}"

# Parse arguments
PUSH=false
MULTIARCH=false
NO_CACHE=false
FIPS=false

while [[ $# -gt 0 ]]; do
    case $1 in
        --push)
            PUSH=true
            shift
            ;;
        --multiarch)
            MULTIARCH=true
            shift
            ;;
        --no-cache)
            NO_CACHE=true
            shift
            ;;
        --fips)
            FIPS=true
            shift
            ;;
        --tag)
            IMAGE_TAG="$2"
            shift 2
            ;;
        --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --push         Push image to registry after build"
            echo "  --multiarch    Build multi-architecture images (amd64, arm64)"
            echo "  --no-cache     Build without using cache"
            echo "  --fips         Build the -fips variant (OpenSSL FIPS provider, tags suffixed -fips)"
            echo "  --tag TAG      Set image tag (default: latest)"
            echo "  --help         Show this help message"
            echo ""
            echo "Environment variables:"
            echo "  IMAGE_NAME     Image name (default: ucm)"
            echo "  REGISTRY       Docker registry (e.g., docker.io/username)"
            echo "  VERSION        UCM version (default: 1.0.0)"
            echo "  PLATFORMS      Target platforms (default: linux/amd64,linux/arm64)"
            exit 0
            ;;
        *)
            echo -e "${RED}Unknown option: $1${NC}"
            echo "Use --help for usage information"
            exit 1
            ;;
    esac
done

# The -fips variant is tagged <tag>-fips and <version>-fips
TAG_SUFFIX=""
if [ "$FIPS" = true ]; then
    TAG_SUFFIX="-fips"
    IMAGE_TAG="${IMAGE_TAG%-fips}$TAG_SUFFIX"
fi

# Construct full image name
if [ -n "$REGISTRY" ]; then
    FULL_IMAGE_NAME="$REGISTRY/$IMAGE_NAME"
else
    FULL_IMAGE_NAME="$IMAGE_NAME"
fi

echo ""
echo -e "${GREEN}📦 Build Configuration:${NC}"
echo "   • Image: $FULL_IMAGE_NAME:$IMAGE_TAG"
echo "   • Version: $VERSION"
echo "   • Multi-arch: $([ "$MULTIARCH" = true ] && echo 'Yes' || echo 'No')"
echo "   • Push: $([ "$PUSH" = true ] && echo 'Yes' || echo 'No')"
echo "   • No cache: $([ "$NO_CACHE" = true ] && echo 'Yes' || echo 'No')"
echo "   • FIPS variant: $([ "$FIPS" = true ] && echo 'Yes' || echo 'No')"
echo ""

# Build arguments
BUILD_ARGS=(
    --build-arg "VERSION=$VERSION"
    --label "org.opencontainers.image.version=$VERSION"
    --label "org.opencontainers.image.created=$(date -u +'%Y-%m-%dT%H:%M:%SZ')"
    --label "org.opencontainers.image.source=https://github.com/NeySlim/ultimate-ca-manager"
)

if [ "$FIPS" = true ]; then
    BUILD_ARGS+=(--build-arg "UCM_FIPS_BUILD=1")
fi

# Add no-cache if requested
if [ "$NO_CACHE" = true ]; then
    BUILD_ARGS+=(--no-cache)
fi

# Build image
echo -e "${BLUE}🔨 Building Docker image...${NC}"
echo ""

if [ "$MULTIARCH" = true ]; then
    # Multi-architecture build requires buildx
    echo -e "${YELLOW}Building for multiple architectures: $PLATFORMS${NC}"
    
    # Create and use buildx builder if not exists
    if ! docker buildx inspect ucm-builder &>/dev/null; then
        echo "Creating buildx builder..."
        docker buildx create --name ucm-builder --use
    else
        docker buildx use ucm-builder
    fi
    
    # Build for multiple platforms
    docker buildx build \
        "${BUILD_ARGS[@]}" \
        --platform "$PLATFORMS" \
        --tag "$FULL_IMAGE_NAME:$IMAGE_TAG" \
        --tag "$FULL_IMAGE_NAME:$VERSION$TAG_SUFFIX" \
        "$([ "$PUSH" = true ] && echo "--push" || echo "--load")" \
        .
else
    # Single architecture build
    docker build \
        "${BUILD_ARGS[@]}" \
        --tag "$FULL_IMAGE_NAME:$IMAGE_TAG" \
        --tag "$FULL_IMAGE_NAME:$VERSION$TAG_SUFFIX" \
        .
fi

if [ $? -eq 0 ]; then
    echo ""
    echo -e "${GREEN}✅ Build successful!${NC}"
    echo ""
    
    # Show image info
    if [ "$MULTIARCH" != true ]; then
        echo -e "${GREEN}📊 Image Information:${NC}"
        docker images "$FULL_IMAGE_NAME:$IMAGE_TAG" --format "table {{.Repository}}:{{.Tag}}\t{{.Size}}\t{{.CreatedAt}}"
        echo ""
    fi
    
    # Push if requested and not multiarch (multiarch already pushed)
    if [ "$PUSH" = true ] && [ "$MULTIARCH" != true ]; then
        echo -e "${BLUE}📤 Pushing image to registry...${NC}"
        docker push "$FULL_IMAGE_NAME:$IMAGE_TAG"
        docker push "$FULL_IMAGE_NAME:$VERSION$TAG_SUFFIX"
        echo -e "${GREEN}✅ Push successful!${NC}"
    fi
    
    echo ""
    echo -e "${GREEN}🎉 Docker build complete!${NC}"
    echo ""
    echo "To run the container:"
    echo "  docker run -d -p 8443:8443 --name ucm $FULL_IMAGE_NAME:$IMAGE_TAG"
    echo ""
    echo "Or using docker-compose:"
    echo "  docker-compose up -d"
    echo ""
else
    echo ""
    echo -e "${RED}❌ Build failed!${NC}"
    exit 1
fi
