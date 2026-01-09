#!/bin/bash
# Generate Debian changelog from git commits

set -e

VERSION="$1"
if [ -z "$VERSION" ]; then
    echo "Usage: $0 <version>"
    echo "Example: $0 1.8.0-beta"
    exit 1
fi

CHANGELOG_FILE="packaging/debian/changelog"

# Get last tag or first commit
LAST_TAG=$(git describe --tags --abbrev=0 2>/dev/null || git rev-list --max-parents=0 HEAD)

echo "Generating changelog from $LAST_TAG to HEAD..."

# Start changelog
cat > "$CHANGELOG_FILE" <<EOF
ucm ($VERSION) unstable; urgency=medium

EOF

# Add features
echo "  * New features:" >> "$CHANGELOG_FILE"
git log --pretty=format:"    - %s" "$LAST_TAG"..HEAD | grep "^    - feat:" | sed 's/feat: //' >> "$CHANGELOG_FILE" || echo "    (none)" >> "$CHANGELOG_FILE"

echo "" >> "$CHANGELOG_FILE"

# Add fixes
echo "  * Bug fixes:" >> "$CHANGELOG_FILE"
git log --pretty=format:"    - %s" "$LAST_TAG"..HEAD | grep "^    - fix:" | sed 's/fix: //' >> "$CHANGELOG_FILE" || echo "    (none)" >> "$CHANGELOG_FILE"

echo "" >> "$CHANGELOG_FILE"

# Add other changes
echo "  * Other changes:" >> "$CHANGELOG_FILE"
git log --pretty=format:"    - %s" "$LAST_TAG"..HEAD | grep -v "^    - feat:" | grep -v "^    - fix:" | head -10 >> "$CHANGELOG_FILE" || echo "    (none)" >> "$CHANGELOG_FILE"

echo "" >> "$CHANGELOG_FILE"

# Footer
cat >> "$CHANGELOG_FILE" <<EOF

 -- UCM Development Team <dev@ucm-project.org>  $(date -R)
EOF

echo "✓ Changelog generated: $CHANGELOG_FILE"
cat "$CHANGELOG_FILE"
