#!/bin/sh
# Creates a venv at $1 holding only the hash-pinned schema validator of the release SBOMs.
set -eu
dir=${1:?usage: sbom-venv.sh <venv dir>}
here=$(cd "$(dirname "$0")" && pwd)
python3 -m venv "$dir"
"$dir/bin/pip" install --quiet --disable-pip-version-check --require-hashes --no-deps --only-binary :all: \
    -r "$here/sbom-data/requirements.txt"
"$dir/bin/python" -c 'import jsonschema, referencing'
