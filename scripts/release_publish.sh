#!/usr/bin/env bash
#
# UCM release publisher — generic wrapper around `gh release`.
#
# Reads VERSION from the repo, extracts the matching CHANGELOG section,
# waits for the v<version> tag's CI artifacts to be available, then creates
# (or edits) the GitHub release with those notes.
#
# Usage:
#   scripts/release_publish.sh                   # uses VERSION file
#   scripts/release_publish.sh 2.143             # explicit version
#   scripts/release_publish.sh 2.144-rc1 --pre   # mark as prerelease
#   scripts/release_publish.sh --draft           # create as draft
#   scripts/release_publish.sh --edit            # edit existing release notes
#
# Requires: gh, git. Repository must be the current working directory.
set -euo pipefail

REPO_ROOT="$(git rev-parse --show-toplevel)"
cd "$REPO_ROOT"

VERSION=""
PRERELEASE=0
DRAFT=0
EDIT=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --pre|--prerelease) PRERELEASE=1; shift ;;
        --draft)            DRAFT=1; shift ;;
        --edit)             EDIT=1; shift ;;
        -h|--help)          sed -n '2,15p' "$0"; exit 0 ;;
        -*)                 echo "Unknown flag: $1" >&2; exit 2 ;;
        *)                  VERSION="$1"; shift ;;
    esac
done

if [[ -z "$VERSION" ]]; then
    [[ -f VERSION ]] || { echo "VERSION file not found and no version arg given" >&2; exit 2; }
    VERSION="$(tr -d '[:space:]' < VERSION)"
fi

TAG="v${VERSION}"

# Auto-mark RC versions as prerelease unless caller already did.
if [[ "$VERSION" == *-rc* && $PRERELEASE -eq 0 ]]; then
    PRERELEASE=1
    echo "note: $VERSION contains '-rc', marking as prerelease automatically"
fi

# Sanity: tag must exist on remote.
if ! git ls-remote --tags origin "refs/tags/${TAG}" | grep -q "$TAG"; then
    echo "Tag ${TAG} is not on origin. Push the tag first." >&2
    exit 1
fi

# Extract changelog section for this version (same extractor as the workflow).
NOTES="$(python3 scripts/ci/release_version.py notes "$VERSION" CHANGELOG.md | sed -e 's/[[:space:]]*$//')"
if [[ -z "${NOTES//[[:space:]]/}" ]]; then
    echo "No CHANGELOG section found for [${VERSION}]." >&2
    echo "Add a '## [${VERSION}] - YYYY-MM-DD' block to CHANGELOG.md first." >&2
    exit 1
fi

# `latest` only for the highest stable tag on origin (same rule as the workflow).
LATEST="$(git ls-remote --tags --refs origin 'refs/tags/v*' | cut -f2 | python3 scripts/ci/release_version.py latest "$VERSION")"

NOTES_FILE="$(mktemp -t ucm-relnotes.XXXXXX.md)"
trap 'rm -f "$NOTES_FILE"' EXIT
{
    echo "## UCM ${VERSION}"
    echo
    echo "$NOTES"
} > "$NOTES_FILE"

GH_FLAGS=()
[[ $PRERELEASE -eq 1 ]] && GH_FLAGS+=(--prerelease)
[[ $DRAFT -eq 1 ]]      && GH_FLAGS+=(--draft)

if gh release view "$TAG" >/dev/null 2>&1; then
    if [[ $EDIT -eq 1 ]]; then
        echo "Editing existing release ${TAG}..."
        gh release edit "$TAG" --notes-file "$NOTES_FILE" "${GH_FLAGS[@]}"
    else
        echo "Release ${TAG} already exists. Re-run with --edit to update notes." >&2
        gh release view "$TAG" --json url,isDraft,isPrerelease,publishedAt
        exit 0
    fi
else
    echo "Creating release ${TAG}..."
    gh release create "$TAG" \
        --title "UCM ${VERSION}" \
        --notes-file "$NOTES_FILE" \
        --verify-tag \
        "--latest=${LATEST}" \
        "${GH_FLAGS[@]}"
fi

echo
echo "Release URL:"
gh release view "$TAG" --json url -q .url
