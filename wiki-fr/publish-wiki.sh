#!/bin/bash
#
# UCM Wiki Publisher
# Automatically publishes wiki pages to GitHub
#

set -e

WIKI_DIR="/root/ucm-src/wiki"
TEMP_DIR="/tmp/ucm-wiki-publish"
WIKI_REPO="https://github.com/NeySlim/ultimate-ca-manager.wiki.git"

echo "================================================"
echo "   UCM Wiki Publisher"
echo "================================================"
echo ""

# Check if wiki files exist
if [ ! -d "$WIKI_DIR" ]; then
    echo "❌ Error: Wiki directory not found: $WIKI_DIR"
    exit 1
fi

# Count wiki pages
PAGE_COUNT=$(find "$WIKI_DIR" -maxdepth 1 -name "*.md" ! -name "README.md" | wc -l)
echo "📄 Found $PAGE_COUNT wiki pages to publish"
echo ""

# List pages
echo "Pages:"
find "$WIKI_DIR" -maxdepth 1 -name "*.md" ! -name "README.md" -exec basename {} \; | sort
echo ""

# Confirm
read -p "📤 Publish these pages to GitHub Wiki? (y/N): " -n 1 -r
echo ""
if [[ ! $REPLY =~ ^[Yy]$ ]]; then
    echo "❌ Cancelled"
    exit 0
fi

# Clean temp directory
echo "🧹 Cleaning temp directory..."
rm -rf "$TEMP_DIR"
mkdir -p "$TEMP_DIR"

# Clone wiki repository
echo "📥 Cloning wiki repository..."
cd "$TEMP_DIR"
if ! git clone "$WIKI_REPO" wiki; then
    echo ""
    echo "❌ Error: Failed to clone wiki repository"
    echo ""
    echo "Make sure:"
    echo "  1. Wiki is enabled in repository settings"
    echo "  2. At least one page exists (create Home page manually first)"
    echo "  3. You have push access to the repository"
    echo ""
    echo "Enable wiki here:"
    echo "  https://github.com/NeySlim/ultimate-ca-manager/settings"
    exit 1
fi

cd wiki

# Copy wiki files
echo "📋 Copying wiki pages..."
cp "$WIKI_DIR"/*.md . 2>/dev/null || true
rm -f README.md  # Don't publish README to wiki

# Count copied files
COPIED=$(ls -1 *.md 2>/dev/null | wc -l)
echo "✅ Copied $COPIED pages"

# Git add
echo "➕ Adding files to git..."
git add *.md

# Check if there are changes
if git diff --staged --quiet; then
    echo "✅ No changes to publish (wiki is up to date)"
    rm -rf "$TEMP_DIR"
    exit 0
fi

# Show what will be committed
echo ""
echo "📊 Changes to be committed:"
git status --short
echo ""

# Commit
echo "💾 Committing changes..."
COMMIT_MSG="docs: Update wiki documentation

Published pages:
$(ls -1 *.md | sed 's/^/- /')

Total: $COPIED pages
Generated: $(date +'%Y-%m-%d %H:%M:%S')
"

git commit -m "$COMMIT_MSG"

# Push
echo "📤 Pushing to GitHub..."
if git push origin master; then
    echo ""
    echo "================================================"
    echo "   ✅ Wiki Published Successfully!"
    echo "================================================"
    echo ""
    echo "📚 View your wiki:"
    echo "   https://github.com/NeySlim/ultimate-ca-manager/wiki"
    echo ""
    echo "📄 Published pages: $COPIED"
    echo ""
else
    echo ""
    echo "❌ Error: Failed to push to GitHub"
    echo ""
    echo "Check:"
    echo "  1. Git credentials are configured"
    echo "  2. You have push access"
    echo "  3. Wiki repository is accessible"
    exit 1
fi

# Cleanup
echo "🧹 Cleaning up..."
rm -rf "$TEMP_DIR"

echo "✅ Done!"
