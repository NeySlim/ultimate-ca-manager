# UCM pivot guard, embedded at build time into the DEB preinst and the RPM %pre.
# POSIX sh only, no external command: it runs before the package unpacks anything.
# 3.0 upgrades a database last started by 2.254, so it installs over 2.254 or later only.

# 0 when the installed version (empty: none) may be upgraded, 1 otherwise.
# Only major.build is compared: 2.254~rc1 records the same migrations as 2.254.
ucm_pivot_version_ok() {
    ucm_pv=$1
    [ -n "$ucm_pv" ] || return 0
    case $ucm_pv in
        *:*) ucm_pv=${ucm_pv#*:} ;;
    esac
    ucm_major=${ucm_pv%%[!0-9]*}
    [ -n "$ucm_major" ] || return 1
    [ "$ucm_major" -gt 2 ] && return 0
    [ "$ucm_major" -eq 2 ] || return 1
    ucm_rest=${ucm_pv#"$ucm_major"}
    case $ucm_rest in
        .[0-9]*) ucm_rest=${ucm_rest#.} ;;
        *) return 1 ;;
    esac
    ucm_build=${ucm_rest%%[!0-9]*}
    [ "$ucm_build" -ge 254 ]
}

# Refuses, on stderr, a version older than 2.254: the one installed, or with "removed"
# as $2 the one a removal left the configuration and data of
ucm_pivot_guard() {
    ucm_pivot_version_ok "$1" && return 0
    if [ "$2" = removed ]; then
        echo "UCM $1 was removed, its configuration and data remain, and this package" >&2
        echo "upgrades UCM 2.254 or later only:" >&2
    else
        echo "UCM $1 is installed, and this package upgrades UCM 2.254 or later only:" >&2
    fi
    echo "its database must have been started by 2.254 first." >&2
    echo "Install 2.254, start it once, then install this package." >&2
    if [ "$2" = removed ]; then
        echo "Nothing was changed." >&2
    else
        echo "Nothing was changed: UCM $1 is still installed." >&2
    fi
    return 1
}
