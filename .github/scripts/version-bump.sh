#!/bin/bash
# Auto-versioning based on conventional commits
# Analyzes commit messages since last tag to determine version bump

set -e

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m'

# Get last tag
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "v0.0.0")
echo -e "${CYAN}Last tag: $LAST_TAG${NC}"

# Remove 'v' prefix and split version
VERSION=${LAST_TAG#v}
IFS='.' read -r MAJOR MINOR PATCH <<< "$VERSION"

# Remove any suffix (like -beta, -rc1)
PATCH=${PATCH%%-*}

echo -e "${CYAN}Current version: $MAJOR.$MINOR.$PATCH${NC}"

# Analyze commits since last tag
COMMITS=$(git log $LAST_TAG..HEAD --pretty=format:"%s" 2>/dev/null || git log --pretty=format:"%s")

# Check for breaking changes
if echo "$COMMITS" | grep -q "BREAKING CHANGE:"; then
    BUMP="major"
    echo -e "${RED}Breaking changes detected → MAJOR bump${NC}"
# Check for features
elif echo "$COMMITS" | grep -q "^feat"; then
    BUMP="minor"
    echo -e "${GREEN}New features detected → MINOR bump${NC}"
# Check for fixes
elif echo "$COMMITS" | grep -q "^fix"; then
    BUMP="patch"
    echo -e "${YELLOW}Bug fixes detected → PATCH bump${NC}"
else
    BUMP="patch"
    echo -e "${YELLOW}Other changes detected → PATCH bump (default)${NC}"
fi

# Calculate new version
case $BUMP in
    major)
        MAJOR=$((MAJOR + 1))
        MINOR=0
        PATCH=0
        ;;
    minor)
        MINOR=$((MINOR + 1))
        PATCH=0
        ;;
    patch)
        PATCH=$((PATCH + 1))
        ;;
esac

NEW_VERSION="$MAJOR.$MINOR.$PATCH"
NEW_TAG="v$NEW_VERSION"

echo -e "${GREEN}New version: $NEW_VERSION${NC}"
echo -e "${GREEN}New tag: $NEW_TAG${NC}"

# Output for GitHub Actions
if [ -n "$GITHUB_OUTPUT" ]; then
    echo "version=$NEW_VERSION" >> "$GITHUB_OUTPUT"
    echo "tag=$NEW_TAG" >> "$GITHUB_OUTPUT"
    echo "bump=$BUMP" >> "$GITHUB_OUTPUT"
fi

# If --create-tag flag is provided, create the tag
if [ "$1" = "--create-tag" ]; then
    echo ""
    echo -e "${YELLOW}Creating tag $NEW_TAG...${NC}"
    git tag -a "$NEW_TAG" -m "Release $NEW_VERSION"
    echo -e "${GREEN}✓ Tag created${NC}"
    echo ""
    echo "Push with: git push origin $NEW_TAG"
fi
