#!/usr/bin/env bash
# SBOM of one pushed image platform, read from the image pulled by its digest: Trivy lists the OS
# packages, scripts/ci/sbom.py reads the exported filesystem (nothing in the image is run).
# Env: VERSION, DIGEST (sha256:...), REPOSITORY, ARCH, FRONTEND (frontend build record), RUNNER_TEMP.
set -euo pipefail
variant=${1:?usage: sbom-image.sh standard|fips}
here=$(cd "$(dirname "$0")" && pwd)
work="$RUNNER_TEMP/sbom-work"
out="$RUNNER_TEMP/sbom"
mkdir -p "$work" "$out"
[[ "$DIGEST" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "::error::not an image digest: $DIGEST"; exit 1; }
ref="$REPOSITORY@$DIGEST"

"$here/sbom-venv.sh" "$work/venv"
"$here/install-trivy.sh" "$work/bin" "$ARCH"
docker pull --quiet "$ref"
docker image inspect "$ref" > "$work/config.json"
"$work/bin/trivy" image --quiet --image-src docker --format cyclonedx --pkg-types os \
    --output "$work/trivy.cdx.json" "$ref"
cid=$(docker create "$ref")
trap 'docker rm -f "$cid" >/dev/null' EXIT
docker export "$cid" | "$work/venv/bin/python" "$here/sbom.py" image --rootfs-tar - \
    --image-config "$work/config.json" --trivy "$work/trivy.cdx.json" --digest "$DIGEST" \
    --repository "$REPOSITORY" --variant "$variant" --arch "$ARCH" --dockerfile "$here/../../Dockerfile" \
    --frontend "$FRONTEND" --version "$VERSION" --commit "$GITHUB_SHA" -o "$out"
ls -l "$out"
