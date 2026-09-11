#!/bin/sh
#
# Strip a staged copy of backend/ from everything a working checkout leaves
# behind. Shared by the Debian rules and the local RPM build so the two cannot
# drift apart: a package built from a live checkout used to carry the
# database, the sessions and the private keys sitting under backend/data.
#
# The tracked, empty data/ skeleton stays. The unit names
# /opt/ucm/backend/data in its ReadWritePaths, and systemd refuses to start
# when a path listed there does not exist.
#
set -e

BACKEND=${1:?usage: prune-runtime-state.sh <staged backend directory>}
[ -d "$BACKEND" ] || { echo "prune-runtime-state.sh: $BACKEND is not a directory" >&2; exit 1; }

# Runtime and development leftovers
rm -rf "$BACKEND/venv" "$BACKEND/.venv" "$BACKEND/env" "$BACKEND/ENV" "$BACKEND/logs"
find "$BACKEND" -type d \
     \( -name __pycache__ -o -name .pytest_cache -o -name coverage_html \
        -o -name .ruff_cache -o -name .mypy_cache -o -name htmlcov \) \
     -prune -exec rm -rf {} +

# Stray logs, coverage files and databases a run leaves at the root of the
# tree. Nothing under version control matches these, and the container image
# ignores the same shapes, so the three package formats agree.
find "$BACKEND" -type f \
     \( -name '*.log' -o -name '*.db' -o -name '*.db-journal' -o -name .coverage \) \
     -delete

# Configuration belongs to the installed system, not to the package, at any
# depth: the RPM spec already swept these recursively
find "$BACKEND" -name '.env*' ! -name '.env*.example' -type f -delete

# Everything the server wrote under data/, keeping the tracked skeleton
# A symbolic link would ship as an absolute path into the build machine, and
# the directory the unit expects would simply not be there
if [ -L "$BACKEND/data" ]; then
    rm -f "$BACKEND/data"
fi
if [ -d "$BACKEND/data" ]; then
    # Symbolic links go too: one pointing at the build machine would ship as a
    # dangling absolute path
    find "$BACKEND/data" -mindepth 1 \( -type f -o -type l \) ! -name .gitkeep -delete
    find "$BACKEND/data" -mindepth 1 -type d -empty -delete
fi
# The directory itself must exist whatever the staged copy held: the unit names
# /opt/ucm/backend/data in its ReadWritePaths
mkdir -p "$BACKEND/data"
