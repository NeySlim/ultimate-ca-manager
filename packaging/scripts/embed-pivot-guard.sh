#!/bin/sh
# Replaces the single line "# @UCM_PIVOT_GUARD@" of a package script with pivot-guard.sh.
# In an RPM spec each % is doubled, which rpm expands back to one in the scriptlet.
set -eu

target=$1
guard="$(dirname "$0")/pivot-guard.sh"
marker='# @UCM_PIVOT_GUARD@'
[ -f "$guard" ] || { echo "embed-pivot-guard: $guard is missing" >&2; exit 1; }

if [ "$(grep -c -x -F "$marker" "$target")" != 1 ]; then
    echo "embed-pivot-guard: $target must hold the line '$marker' exactly once" >&2
    exit 1
fi
spec=0
case $target in
    *.spec) spec=1 ;;
esac

tmp="$target.pivot-guard"
awk -v guard="$guard" -v marker="$marker" -v spec="$spec" '
    $0 == marker {
        while ((getline line < guard) > 0) {
            if (spec == 1) gsub(/%/, "%%", line)
            print line
        }
        close(guard)
        next
    }
    { print }
' "$target" > "$tmp"
# Rewritten in place so the script keeps its mode
cat "$tmp" > "$target"
rm -f "$tmp"
