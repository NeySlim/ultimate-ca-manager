#!/usr/bin/env bash
#
# UCM release publisher — generic wrapper around `gh release`.
#
# Reads VERSION from the repo, extracts the matching CHANGELOG section and
# edits the notes of the existing GitHub release. A release is only created by
# the Build & Release workflow, which attaches every deliverable with its SBOM.
#
# Usage:
#   scripts/release_publish.sh --edit            # uses VERSION file
#   scripts/release_publish.sh 2.143 --edit      # explicit version
#   scripts/release_publish.sh 2.144-rc1 --pre --edit   # mark as prerelease
#
# Requires: gh, git, python3 (scripts/ci/release_version.py). Repository must be the current working directory.
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
        -h|--help)          sed -n '2,13p' "$0"; exit 0 ;;
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

# A release page resolves no relative link: the notes link the CHANGELOG of the tag on GitHub.
REPO="$(gh repo view --json nameWithOwner -q .nameWithOwner)" && [[ -n "$REPO" ]] || {
    echo "gh names no GitHub repository for this checkout: the notes would link no CHANGELOG." >&2
    exit 1
}
CHANGELOG_URL="https://github.com/${REPO}/blob/${TAG}/CHANGELOG.md"

# Same rule as the workflow (release_version.py): its own section, else [Unreleased] for a RC.
NOTES="$(python3 scripts/ci/release_version.py notes "$VERSION" CHANGELOG.md --changelog-url "$CHANGELOG_URL" \
    | sed -e 's/[[:space:]]*$//')" || {
    if [[ "$VERSION" == *-rc* ]]; then
        echo "CHANGELOG.md needs '## [${VERSION}]' or '## [Unreleased]' with entries." >&2
    else
        echo "CHANGELOG.md needs '## [${VERSION}]' with entries." >&2
    fi
    exit 1
}

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
    # Created here, a release would carry no package, image SBOM or checksum
    echo "Release ${TAG} does not exist: the Build & Release workflow of the tag creates it." >&2
    exit 1
fi

echo
echo "Release URL:"
gh release view "$TAG" --json url -q .url
