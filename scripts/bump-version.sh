#!/bin/bash
# Centralized version bump
# Source of truth: git tag (CI) → VERSION file (dev/runtime)
# Usage: ./scripts/bump-version.sh 2.1.0-beta5
#
# In CI (build-release.yml), the tag drives VERSION automatically.
# This script is for local dev to keep VERSION + package.json in sync.

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -z "$1" ]; then
  echo "Usage: $0 <version>"
  echo "Current: $(cat "$ROOT_DIR/VERSION" 2>/dev/null || echo 'not set')"
  exit 1
fi

VERSION="$1"

# 1. VERSION file at repo root (read by backend at runtime)
echo "$VERSION" > "$ROOT_DIR/VERSION"

# 2. frontend/package.json (read by vite at build time)
sed -i "s/\"version\": \".*\"/\"version\": \"$VERSION\"/" "$ROOT_DIR/frontend/package.json"

echo "✅ Version updated to $VERSION"
echo "   - VERSION"
echo "   - frontend/package.json"
