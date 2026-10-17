#!/bin/bash
# Update all hardcoded version references in the UCM wiki.
# Usage: ./update-wiki-versions.sh 2.113
#
# This updates:
#   - **Version:** headers
#   - Docker pull commands
#   - DEB/RPM download URLs and install commands
#   - API docs version strings
#   - Version badge on Home.md
#   - "Latest Stable" table row
#
# It does NOT touch:
#   - Historical "(vX.Y)" references (feature introduction dates)
#   - Release-Notes-*.md files
#   - Building.md examples

set -euo pipefail

NEW_VERSION="${1:?Usage: $0 <version>  (e.g., 2.113)}"
WIKI_DIR="${2:-/root/ucm-wiki}"

cd "$WIKI_DIR"

echo "📝 Updating wiki to v${NEW_VERSION}..."

# 1. Version badge
sed -i "s|version-[0-9.]*-brightgreen|version-${NEW_VERSION}-brightgreen|g" Home.md

# 2. Docker pull
sed -i "s|docker pull neyslim/ultimate-ca-manager:[0-9.]*|docker pull neyslim/ultimate-ca-manager:${NEW_VERSION}|g" Home.md Installation-Guide.md

sed -i "s|docker pull ghcr.io/neyslim/ultimate-ca-manager:[0-9.]*|docker pull ghcr.io/neyslim/ultimate-ca-manager:${NEW_VERSION}|g" Home.md Installation-Guide.md

# 3. DEB download URLs
for f in Home.md Quick-Start.md Installation-Guide.md; do
    [ -f "$f" ] || continue
    sed -i "s|/releases/download/v[0-9.]*/ucm_[0-9.]*_all\.deb|/releases/download/v${NEW_VERSION}/ucm_${NEW_VERSION}_all.deb|g" "$f"
    sed -i "s|dpkg -i ucm_[0-9.]*_all\.deb|dpkg -i ucm_${NEW_VERSION}_all.deb|g" "$f"
done

# 4. RPM download URLs
for f in Home.md Quick-Start.md Installation-Guide.md; do
    [ -f "$f" ] || continue
    for dist in fc43 el9; do
        sed -i "s|/releases/download/v[0-9.]*/ucm-[0-9.]*-1\.$dist\.noarch\.rpm|/releases/download/v${NEW_VERSION}/ucm-${NEW_VERSION}-1.$dist.noarch.rpm|g" "$f"
        sed -i "s|dnf install \./ucm-[0-9.]*-1\.$dist\.noarch\.rpm|dnf install ./ucm-${NEW_VERSION}-1.$dist.noarch.rpm|g" "$f"
    done
done

# 5. **Version:** headers (all wiki pages except Release Notes and Building)
for f in *.md; do
    [[ "$f" == Release-Notes* ]] && continue
    [[ "$f" == Building.md ]] && continue
    sed -i "s/\*\*Version:\*\* [0-9.]*/\*\*Version:\*\* ${NEW_VERSION}/g" "$f"
done

# 6. API version strings
sed -i "s/\"version\": \"[0-9.]*\"/\"version\": \"${NEW_VERSION}\"/g" API-Documentation.md API-Reference.md Architecture.md Monitoring.md 2>/dev/null || true

# 7. API docs title
sed -i "s/Ultimate Certificate Manager v[0-9.]*/Ultimate Certificate Manager v${NEW_VERSION}/g" API-Documentation.md API-Reference.md 2>/dev/null || true

# 8. Latest Stable table
sed -i "s/| Latest Stable | [0-9.]* |/| Latest Stable | ${NEW_VERSION} |/" Home.md

# Summary
UPDATED=$(git diff --name-only | wc -l)
echo "✅ Updated ${UPDATED} files to v${NEW_VERSION}"
echo ""
echo "Next steps:"
echo "  cd ${WIKI_DIR}"
echo "  git diff --stat"
echo "  git add -A && git commit -m 'docs: update versions to ${NEW_VERSION}'"
echo "  git push origin master"
