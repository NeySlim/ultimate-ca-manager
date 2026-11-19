#!/usr/bin/env bash
# apt-get install for CI runners, with fallback mirrors when the Ubuntu archive hosts are unreachable.
# Usage: scripts/ci/apt-install.sh <package>...
# Packages stay verified by apt against the archive signing keys, whichever mirror serves them.
set -u

[ "$#" -gt 0 ] || { echo "usage: $0 <package>..." >&2; exit 2; }

MIRRORS="${UCM_APT_FALLBACK_MIRRORS:-https://mirrors.kernel.org/ubuntu https://mirror.math.princeton.edu/pub/ubuntu https://mirror.csclub.uwaterloo.ca/ubuntu https://ftp.halifax.rwth-aachen.de/ubuntu}"
SUDO=""; [ "$(id -u)" = 0 ] || SUDO="sudo"
APT="$SUDO env DEBIAN_FRONTEND=noninteractive apt-get -o Acquire::Retries=2 -o Acquire::http::Timeout=20 -o Acquire::https::Timeout=20"

install() {
  # Error-Mode=any: an index that could not be fetched fails the update instead of a warning.
  $APT -o APT::Update::Error-Mode=any update && $APT install -y "$@"
}

install "$@" && exit 0

if [ "$(dpkg --print-architecture)" != "amd64" ]; then
  echo "apt-install: the archive is unreachable and the fallback mirrors only carry amd64" >&2
  exit 1
fi

use_mirror() { # $1 = mirror base URL
  if [ -f /etc/apt/apt-mirrors.txt ]; then
    # GitHub-hosted runners: the sources point at this list.
    printf '%s/\n' "$1" | $SUDO tee /etc/apt/apt-mirrors.txt > /dev/null
  else
    for f in /etc/apt/sources.list /etc/apt/sources.list.d/*.sources /etc/apt/sources.list.d/*.list; do
      [ -f "$f" ] || continue
      $SUDO sed -i -E "s#https?://([a-z0-9.-]+\.)?(archive|security)\.ubuntu\.com/ubuntu/?#$1/#g" "$f"
    done
  fi
}

for mirror in $MIRRORS; do
  echo "::warning::apt: Ubuntu archive unreachable, retrying on $mirror"
  use_mirror "$mirror"
  install "$@" && exit 0
done

echo "apt-install: the archive and every fallback mirror failed" >&2
exit 1
