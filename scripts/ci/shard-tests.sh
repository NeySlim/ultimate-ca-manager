#!/bin/sh
# Prints shard K of N of the backend test files, one per line; run from backend/.
# Usage: shard-tests.sh K N [LIST]   LIST: a file of globs, one per line (default: every test file).
# Files are dealt by measured duration (test-durations.txt beside this script, "seconds path";
# SHARD_DURATIONS names another): the longest first, each to the lightest shard, and printed
# longest first so pytest-xdist starts them first. A file without a measure weighs the median.
# The shards together are the whole set, once each.
set -eu
k=$1 n=$2 list=${3:-}
durations=${SHARD_DURATIONS:-$(dirname "$0")/test-durations.txt}
if [ "$k" -lt 1 ] || [ "$k" -gt "$n" ]; then echo "shard $k of $n: out of range" >&2; exit 2; fi
if [ -n "$list" ]; then
  files=$(grep -v -e '^[[:space:]]*#' -e '^[[:space:]]*$' "$list" | while read -r glob; do
    # A pattern that matches nothing is a renamed or deleted file: fail, never skip.
    ls $glob 2>/dev/null || { echo "$list: no file matches $glob" >&2; exit 1; }
  done)
else
  files=$(find tests -name 'test_*.py')
fi
[ -f "$durations" ] || durations=/dev/null
default=$(grep -v -e '^#' -e '^[[:space:]]*$' "$durations" | awk '{ print $1 }' | LC_ALL=C sort -g \
  | awk '{ v[NR] = $1 } END { if (NR == 0) print 1; else if (NR % 2) print v[(NR + 1) / 2]; else print (v[NR / 2] + v[NR / 2 + 1]) / 2 }')
printf '%s\n' "$files" | LC_ALL=C sort -u \
  | awk -v d="$default" -v f="$durations" '
      BEGIN { while ((getline line < f) > 0) if (line !~ /^#/ && split(line, a, " ") == 2) w[a[2]] = a[1] }
      NF { print ($0 in w ? w[$0] : d) "\t" $0 }' \
  | LC_ALL=C sort -t "$(printf '\t')" -k1,1gr -k2,2 \
  | awk -F '\t' -v k="$k" -v n="$n" 'BEGIN { for (s = 1; s <= n; s++) load[s] = 0 }
    {
      best = 1
      for (s = 2; s <= n; s++) if (load[s] < load[best]) best = s
      load[best] += $1
      if (best == k) print $2
    }'
