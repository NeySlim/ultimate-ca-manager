#!/bin/sh
# Installs the Trivy release named here into $1, after checking the archive against the
# SHA-256 written here (not one downloaded next to it). Linux amd64 and arm64.
set -eu
TRIVY_VERSION=0.70.0
TRIVY_SHA256_AMD64=8b4376d5d6befe5c24d503f10ff136d9e0c49f9127a4279fd110b727929a5aa9
TRIVY_SHA256_ARM64=2f6bb988b553a1bbac6bdd1ce890f5e412439564e17522b88a4541b4f364fc8d

dest=${1:?usage: install-trivy.sh <directory> [amd64|arm64]}
arch=${2:-$(uname -m)}
case "$arch" in
    amd64|x86_64) asset=Linux-64bit; sum=$TRIVY_SHA256_AMD64 ;;
    arm64|aarch64) asset=Linux-ARM64; sum=$TRIVY_SHA256_ARM64 ;;
    *) echo "install-trivy: unsupported architecture $arch" >&2; exit 1 ;;
esac
mkdir -p "$dest"
archive="$dest/trivy.tar.gz"
curl -fsSL -o "$archive" \
    "https://github.com/aquasecurity/trivy/releases/download/v${TRIVY_VERSION}/trivy_${TRIVY_VERSION}_${asset}.tar.gz"
echo "$sum  $archive" | sha256sum -c - >/dev/null || { echo "install-trivy: checksum mismatch" >&2; exit 1; }
tar -xzf "$archive" -C "$dest" trivy
rm -f "$archive"
"$dest/trivy" --version | grep -qx "Version: $TRIVY_VERSION"
