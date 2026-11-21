#!/bin/sh
# Prints the test files of one shard of the HA bench, one per line; run from backend/.
# Usage: ha-bench-shard.sh SHARD | --list   "rest" is every test_*.py under tests/ha no other
# shard names, so a new file always runs. A named file that is gone fails, never skips.
set -eu
crash_crl="tests/ha/test_crash_crl.py"
jobs="tests/ha/test_jobs.py"
restore="tests/ha/test_restore.py tests/ha/test_restore_files.py tests/ha/test_restore_files_task.py tests/ha/test_backups.py tests/ha/test_rolling_restart.py"
case "${1:-}" in
  --list) printf '%s\n' crash-crl jobs restore rest; exit 0 ;;
  crash-crl) files=$crash_crl ;;
  jobs) files=$jobs ;;
  restore) files=$restore ;;
  rest)
    files=$(find tests/ha -name 'test_*.py' | sort | while read -r f; do
      case " $crash_crl $jobs $restore " in *" $f "*) ;; *) echo "$f" ;; esac
    done) ;;
  *) echo "usage: ha-bench-shard.sh crash-crl|jobs|restore|rest|--list" >&2; exit 2 ;;
esac
for f in $files; do
  [ -f "$f" ] || { echo "ha-bench-shard: $f is not a file" >&2; exit 1; }
  echo "$f"
done
