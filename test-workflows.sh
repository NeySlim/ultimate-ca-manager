#!/bin/bash
#
# Test GitHub Actions Workflows
# This script helps verify workflows will trigger correctly
#

set -e

REPO="NeySlim/ultimate-ca-manager"

echo "╔══════════════════════════════════════════════════════════════════════════╗"
echo "║           🧪 GITHUB ACTIONS WORKFLOWS - TEST CHECKER                     ║"
echo "╚══════════════════════════════════════════════════════════════════════════╝"
echo ""

# Colors
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if we're in a git repo
if ! git rev-parse --git-dir > /dev/null 2>&1; then
    echo -e "${RED}❌ Not in a git repository${NC}"
    exit 1
fi

echo "Repository: $(git remote get-url origin 2>/dev/null || echo 'No remote')"
echo "Current branch: $(git branch --show-current)"
echo "Last commit: $(git log -1 --oneline)"
echo ""

# Check workflows exist
echo "1️⃣  Checking workflows files..."
echo ""

workflows=(
    ".github/workflows/docker-publish.yml"
    ".github/workflows/release.yml"
    ".github/workflows/ci.yml"
)

all_exist=true
for workflow in "${workflows[@]}"; do
    if [ -f "$workflow" ]; then
        echo -e "   ${GREEN}✅${NC} $(basename $workflow)"
    else
        echo -e "   ${RED}❌${NC} $(basename $workflow) NOT FOUND"
        all_exist=false
    fi
done
echo ""

if [ "$all_exist" = false ]; then
    echo -e "${RED}❌ Some workflows are missing${NC}"
    exit 1
fi

# Check required files
echo "2️⃣  Checking required files..."
echo ""

required_files=(
    "Dockerfile"
    "DOCKERHUB_README.md"
    "backend/requirements.txt"
    ".env.example"
)

for file in "${required_files[@]}"; do
    if [ -f "$file" ]; then
        echo -e "   ${GREEN}✅${NC} $file"
    else
        echo -e "   ${RED}❌${NC} $file NOT FOUND"
    fi
done
echo ""

# Check if changes are pushed
echo "3️⃣  Checking git status..."
echo ""

if git diff-index --quiet HEAD --; then
    echo -e "   ${GREEN}✅ Working directory clean${NC}"
else
    echo -e "   ${YELLOW}⚠️  Uncommitted changes exist${NC}"
    git status --short
fi
echo ""

# Check remote
echo "4️⃣  Checking remote repository..."
echo ""

if git ls-remote --exit-code origin > /dev/null 2>&1; then
    echo -e "   ${GREEN}✅ Remote 'origin' accessible${NC}"
    
    # Check if workflows are pushed
    if git ls-remote --exit-code origin refs/heads/main > /dev/null 2>&1; then
        echo -e "   ${GREEN}✅ Main branch exists on remote${NC}"
        
        # Check if workflows directory is in remote
        if git ls-tree -r origin/main --name-only | grep -q ".github/workflows"; then
            echo -e "   ${GREEN}✅ Workflows pushed to remote${NC}"
        else
            echo -e "   ${RED}❌ Workflows NOT pushed to remote${NC}"
            echo "      Run: git push origin main"
        fi
    else
        echo -e "   ${YELLOW}⚠️  Main branch not found on remote${NC}"
    fi
else
    echo -e "   ${RED}❌ Cannot access remote repository${NC}"
fi
echo ""

# Check tags
echo "5️⃣  Checking tags..."
echo ""

local_tags=$(git tag -l "v*" | wc -l)
echo "   Local tags (v*): $local_tags"

if [ $local_tags -gt 0 ]; then
    echo "   Latest tag: $(git describe --tags --abbrev=0 2>/dev/null || echo 'none')"
fi
echo ""

# Test scenarios
echo "6️⃣  Test scenarios for workflows..."
echo ""

echo "   📝 Scenario 1: Trigger CI workflow"
echo "      Command: git push origin main"
echo "      Expected: ci.yml will run"
echo "      Check: https://github.com/$REPO/actions/workflows/ci.yml"
echo ""

echo "   📝 Scenario 2: Trigger Release + Docker workflows"
echo "      Command: git tag v1.0.2 && git push origin v1.0.2"
echo "      Expected: release.yml + docker-publish.yml will run"
echo "      Check: https://github.com/$REPO/actions"
echo ""

echo "   📝 Scenario 3: Manual Docker build"
echo "      Go to: https://github.com/$REPO/actions/workflows/docker-publish.yml"
echo "      Click: Run workflow"
echo "      Expected: docker-publish.yml will run manually"
echo ""

# Check GitHub CLI
echo "7️⃣  GitHub CLI availability..."
echo ""

if command -v gh &> /dev/null; then
    echo -e "   ${GREEN}✅ GitHub CLI (gh) installed${NC}"
    
    # Try to list workflows (if authenticated)
    if gh auth status &> /dev/null; then
        echo -e "   ${GREEN}✅ Authenticated to GitHub${NC}"
        echo ""
        echo "   Available commands:"
        echo "      gh workflow list"
        echo "      gh run list"
        echo "      gh run watch"
    else
        echo -e "   ${YELLOW}⚠️  Not authenticated to GitHub${NC}"
        echo "      Run: gh auth login"
    fi
else
    echo -e "   ${YELLOW}⚠️  GitHub CLI not installed${NC}"
    echo "      Install: https://cli.github.com/"
fi
echo ""

# Final recommendations
echo "8️⃣  Recommendations..."
echo ""

echo "   Before testing workflows:"
echo "   1. Configure DOCKERHUB_TOKEN in GitHub Secrets"
echo "      → https://github.com/$REPO/settings/secrets/actions"
echo ""
echo "   2. Create Docker Hub repository: ultimate-ca-manager"
echo "      → https://hub.docker.com/repositories"
echo ""
echo "   3. Enable GitHub Actions (if not already enabled)"
echo "      → https://github.com/$REPO/settings/actions"
echo ""
echo "   Test with a test tag first:"
echo "   git tag v1.0.1-test"
echo "   git push origin v1.0.1-test"
echo ""

echo "═══════════════════════════════════════════════════════════════════════════"
echo ""
echo -e "${GREEN}✅ Workflows validation complete!${NC}"
echo ""
echo "Next step: Push a tag to trigger workflows"
echo "Example: git tag v1.0.2 && git push origin v1.0.2"
echo ""
echo "Monitor: https://github.com/$REPO/actions"
echo ""
