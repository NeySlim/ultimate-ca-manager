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

# 2b. frontend/package-lock.json: both occurrences follow package.json
VERSION="$VERSION" LOCK="$ROOT_DIR/frontend/package-lock.json" node -e "const fs=require('fs'); const f=process.env.LOCK; const p=JSON.parse(fs.readFileSync(f,'utf8')); p.version=process.env.VERSION; if (p.packages && p.packages['']) p.packages[''].version=process.env.VERSION; fs.writeFileSync(f, JSON.stringify(p,null,2)+'\n');"

# 3. Helm chart appVersion: the image tag the chart deploys by default.
#    Stable versions only (a -dev/-rc image tag is not published for the chart).
if [[ "$VERSION" =~ ^[0-9]+\.[0-9]+(\.[0-9]+)?$ ]]; then
    sed -i "s/^appVersion: \".*\"/appVersion: \"$VERSION\"/" "$ROOT_DIR/charts/ucm/Chart.yaml"
    CHART_NOTE="   - charts/ucm/Chart.yaml (appVersion)"
fi

echo "✅ Version updated to $VERSION"
echo "   - VERSION"
echo "   - frontend/package.json"
echo "   - frontend/package-lock.json"
if [ -n "${CHART_NOTE:-}" ]; then echo "$CHART_NOTE"; fi
