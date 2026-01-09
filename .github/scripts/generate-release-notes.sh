#!/bin/bash
# Generate release notes from conventional commits

set -e

VERSION="$1"
if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version>"
    exit 1
fi

# Get last tag
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || echo "")

if [ -z "$LAST_TAG" ]; then
    echo "No previous tag found, using all commits"
    RANGE="HEAD"
else
    echo "Generating release notes from $LAST_TAG to HEAD"
    RANGE="$LAST_TAG..HEAD"
fi

# Output file
OUTPUT="RELEASE_NOTES_v${VERSION}.md"

# Start release notes
cat > "$OUTPUT" <<EOF
# UCM v${VERSION}

**Release Date**: $(date +%Y-%m-%d)  
**Docker Image**: \`ghcr.io/neyslim/ultimate-ca-manager:${VERSION}\`

---

EOF

# Features
echo "## 🎉 New Features" >> "$OUTPUT"
echo "" >> "$OUTPUT"
FEATURES=$(git log $RANGE --pretty=format:"* %s (%h)" --grep="^feat" | sed 's/^feat: //' | sed 's/^feat(//' | sed 's/): /: /')
if [ -n "$FEATURES" ]; then
    echo "$FEATURES" >> "$OUTPUT"
else
    echo "* No new features in this release" >> "$OUTPUT"
fi
echo "" >> "$OUTPUT"

# Bug Fixes
echo "## 🐛 Bug Fixes" >> "$OUTPUT"
echo "" >> "$OUTPUT"
FIXES=$(git log $RANGE --pretty=format:"* %s (%h)" --grep="^fix" | sed 's/^fix: //' | sed 's/^fix(//' | sed 's/): /: /')
if [ -n "$FIXES" ]; then
    echo "$FIXES" >> "$OUTPUT"
else
    echo "* No bug fixes in this release" >> "$OUTPUT"
fi
echo "" >> "$OUTPUT"

# Performance Improvements
echo "## ⚡ Performance" >> "$OUTPUT"
echo "" >> "$OUTPUT"
PERF=$(git log $RANGE --pretty=format:"* %s (%h)" --grep="^perf" | sed 's/^perf: //' | sed 's/^perf(//' | sed 's/): /: /')
if [ -n "$PERF" ]; then
    echo "$PERF" >> "$OUTPUT"
else
    echo "* No performance improvements in this release" >> "$OUTPUT"
fi
echo "" >> "$OUTPUT"

# Documentation
echo "## 📚 Documentation" >> "$OUTPUT"
echo "" >> "$OUTPUT"
DOCS=$(git log $RANGE --pretty=format:"* %s (%h)" --grep="^docs" | sed 's/^docs: //' | sed 's/^docs(//' | sed 's/): /: /')
if [ -n "$DOCS" ]; then
    echo "$DOCS" >> "$OUTPUT"
else
    echo "* No documentation changes in this release" >> "$OUTPUT"
fi
echo "" >> "$OUTPUT"

# Breaking Changes
BREAKING=$(git log $RANGE --pretty=format:"%B" --grep="BREAKING CHANGE")
if [ -n "$BREAKING" ]; then
    echo "## ⚠️ BREAKING CHANGES" >> "$OUTPUT"
    echo "" >> "$OUTPUT"
    echo "$BREAKING" | grep "BREAKING CHANGE:" | sed 's/BREAKING CHANGE: //' | sed 's/^/* /' >> "$OUTPUT"
    echo "" >> "$OUTPUT"
fi

# Installation
cat >> "$OUTPUT" <<EOF
---

## 📦 Installation

### Docker

\`\`\`bash
# Pull image
docker pull ghcr.io/neyslim/ultimate-ca-manager:${VERSION}

# Quick start
./docker-helper.sh

# Or with docker-compose
docker-compose up -d
\`\`\`

### Debian/Ubuntu

\`\`\`bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v${VERSION}/ucm_${VERSION}_all.deb
sudo dpkg -i ucm_${VERSION}_all.deb
sudo apt-get install -f
\`\`\`

### From Source

\`\`\`bash
git clone https://github.com/NeySlim/ultimate-ca-manager.git
cd ultimate-ca-manager
git checkout v${VERSION}
# Follow installation instructions in README.md
\`\`\`

---

## ⬆️ Upgrade

### Docker

\`\`\`bash
docker-compose pull
docker-compose up -d
\`\`\`

### DEB Package

\`\`\`bash
wget https://github.com/NeySlim/ultimate-ca-manager/releases/download/v${VERSION}/ucm_${VERSION}_all.deb
sudo dpkg -i ucm_${VERSION}_all.deb
# Database is automatically backed up before upgrade
\`\`\`

---

## 📋 Changelog

EOF

# Get commit count
COMMIT_COUNT=$(git rev-list $RANGE --count 2>/dev/null || echo "0")
echo "* **$COMMIT_COUNT commits** since last release" >> "$OUTPUT"

# Contributors
CONTRIBUTORS=$(git log $RANGE --pretty=format:"%an" | sort -u | wc -l)
echo "* **$CONTRIBUTORS contributors**" >> "$OUTPUT"
echo "" >> "$OUTPUT"

# Full changelog link
if [ -n "$LAST_TAG" ]; then
    echo "**Full Changelog**: https://github.com/NeySlim/ultimate-ca-manager/compare/${LAST_TAG}...v${VERSION}" >> "$OUTPUT"
else
    echo "**Full Changelog**: https://github.com/NeySlim/ultimate-ca-manager/commits/v${VERSION}" >> "$OUTPUT"
fi

echo ""
echo "✓ Release notes generated: $OUTPUT"
cat "$OUTPUT"
