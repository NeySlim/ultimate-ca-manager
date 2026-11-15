#!/bin/bash
# Centralized version bump
# Source of truth: git tag (CI) → VERSION file (dev/runtime)
# Usage: ./scripts/bump-version.sh 3.1-dev   (X.Y, X.Y-rcN, X.Y.Z, X.Y.Z-rcN, or one of these with -dev)
#
# In CI (build-release.yml), the tag drives VERSION automatically.
# This script is for local dev to keep VERSION, the npm files and the chart in sync.
# Requires: node, python3 (scripts/ci/release_version.py).

set -e

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT_DIR="$(dirname "$SCRIPT_DIR")"

if [ -z "$1" ]; then
  echo "Usage: $0 <version>"
  echo "Current: $(cat "$ROOT_DIR/VERSION" 2>/dev/null || echo 'not set')"
  exit 1
fi

VERSION="$1"

# package.json and the lock take the npm form, as the release workflow writes it;
# a version the release grammar refuses stops here, before any file is written
NPM_VERSION="$(python3 "$SCRIPT_DIR/ci/release_version.py" npm "$VERSION")"

# 1. VERSION file at repo root (read by backend at runtime)
echo "$VERSION" > "$ROOT_DIR/VERSION"

# 2. frontend/package.json (read by vite at build time) and both occurrences of the lock
VERSION="$NPM_VERSION" FRONTEND="$ROOT_DIR/frontend" node -e "const fs=require('fs'); for (const n of ['package.json','package-lock.json']) { const f=process.env.FRONTEND+'/'+n; const p=JSON.parse(fs.readFileSync(f,'utf8')); p.version=process.env.VERSION; if (p.packages && p.packages['']) p.packages[''].version=process.env.VERSION; fs.writeFileSync(f, JSON.stringify(p,null,2)+'\n'); }"

# 3. Helm chart appVersion: the image tag the chart deploys by default. The release
#    workflow publishes an image for every tag (stable and RC), none for a -dev version,
#    which leaves appVersion as it is.
#    The chart `version` follows chart changes only.
if [[ "$VERSION" != *-dev ]]; then
    sed -i "s/^appVersion: \".*\"/appVersion: \"$VERSION\"/" "$ROOT_DIR/charts/ucm/Chart.yaml"
    CHART_NOTE="   - charts/ucm/Chart.yaml (appVersion)"
fi

echo "✅ Version updated to $VERSION"
echo "   - VERSION"
echo "   - frontend/package.json"
echo "   - frontend/package-lock.json"
if [ -n "${CHART_NOTE:-}" ]; then echo "$CHART_NOTE"; fi
