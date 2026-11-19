#!/bin/sh
# Prints shard K of N of the backend test files, one per line; run from backend/.
# Usage: shard-tests.sh K N [LIST]   LIST: a file of globs, one per line (default: every test file).
# Files are sorted and dealt round-robin, so the shards together are the whole set, once each.
set -eu
k=$1 n=$2 list=${3:-}
if [ "$k" -lt 1 ] || [ "$k" -gt "$n" ]; then echo "shard $k of $n: out of range" >&2; exit 2; fi
if [ -n "$list" ]; then
  files=$(grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' "$list" | while read -r glob; do
    # A pattern that matches nothing is a renamed or deleted file: fail, never skip.
    ls $glob 2>/dev/null || { echo "$list: no file matches $glob" >&2; exit 1; }
  done)
else
  files=$(find tests -name 'test_*.py')
fi
printf '%s\n' "$files" | LC_ALL=C sort -u | awk -v k="$k" -v n="$n" 'NR % n == k % n'
