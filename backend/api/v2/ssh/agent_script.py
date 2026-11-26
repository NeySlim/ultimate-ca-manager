"""The SSH host agent of issue #451: a POSIX sh script, installed by /ssh/setup/<refid>/agent.

It pulls the KRL of an SSH user CA (RevokedKeys) on a timer, and enrolls the server with a host CA
for a host certificate of its own key (HostCertificate). The agent holds no secret: what it needs
to reach UCM is the URL it was installed from and the CA refids, all public; the single-use
enrollment token is spent at once and never written to disk.
"""
import re

# The URL the installer was fetched from, written into a shell script: nothing a shell reads
_BASE_URL = re.compile(r'^https?://[A-Za-z0-9.\-]+(:[0-9]{1,5})?(/[A-Za-z0-9._~\-/]*)?$|'
                       r'^https?://\[[0-9A-Fa-f:.]+\](:[0-9]{1,5})?(/[A-Za-z0-9._~\-/]*)?$')
_REFID = re.compile(r'^[A-Za-z0-9-]{1,64}$')


def shell_safe_base_url(url):
    """*url* without its trailing slash when a shell can hold it as a literal, else None."""
    url = (url or '').rstrip('/')
    return url if _BASE_URL.match(url) else None


AGENT = r'''#!/bin/sh
# ucm-ssh-agent: keeps this server's sshd in step with UCM (Ultimate Certificate Manager).
#   ucm-ssh-agent sync        pull the KRL now (the timer runs this every INTERVAL minutes)
#   ucm-ssh-agent enroll REFID [NAME...]   exchange UCM_ENROLL_TOKEN for a host certificate
#   ucm-ssh-agent status      show what is installed
#   ucm-ssh-agent uninstall   remove the agent, its timer and its sshd settings
# It holds no secret. Configuration: /etc/ssh/ucm/agent.conf (KEY=value lines).
set -eu
umask 022

ROOT=${UCM_AGENT_ROOT:-}
CONF_DIR="$ROOT/etc/ssh/ucm"
CONF="$CONF_DIR/agent.conf"
AGENT="$ROOT/usr/local/sbin/ucm-ssh-agent"
SSH_DIR="$ROOT/etc/ssh"
SSHD_CONFIG="${UCM_SSHD_CONFIG:-$SSH_DIR/sshd_config}"
DROPIN_DIR="$SSH_DIR/sshd_config.d"
DROPIN="$DROPIN_DIR/40-ucm-ssh-agent.conf"
KRL_FILE="$CONF_DIR/revoked_keys"
UNIT_DIR="$ROOT/etc/systemd/system"
CRON_FILE="$ROOT/etc/cron.d/ucm-ssh-agent"
BEGIN_MARK="# BEGIN ucm-ssh-agent: managed block, removed by ucm-ssh-agent uninstall"
END_MARK="# END ucm-ssh-agent"

log() { printf 'ucm-ssh-agent: %s\n' "$*" >&2; }
die() { log "$*"; exit 1; }
have() { command -v "$1" >/dev/null 2>&1; }

# --- configuration: KEY=value lines, read with sed, never sourced
conf_get() {
    if [ -f "$CONF" ]; then sed -n "s/^$1=//p" "$CONF" | tail -n 1; fi
}
conf_set() {
    mkdir -p "$CONF_DIR"
    [ -f "$CONF" ] || : > "$CONF"
    tmp="$CONF.tmp.$$"
    grep -v "^$1=" "$CONF" > "$tmp" || true
    if [ -n "$2" ]; then printf '%s=%s\n' "$1" "$2" >> "$tmp"; fi
    chmod 600 "$tmp"
    mv -f "$tmp" "$CONF"
}

# --- HTTP: curl, else wget. http_get URL OUT [ETAG] prints the status (000: no answer)
http_get() {
    url=$1 out=$2 etag=${3:-}
    cacert=$(conf_get CA_BUNDLE)
    if have curl; then
        set -- -sS --max-time 60 -o "$out" -w '%{http_code}'
        if [ -n "$cacert" ]; then set -- "$@" --cacert "$cacert"; fi
        if [ -n "$etag" ]; then set -- "$@" -H "If-None-Match: $etag"; fi
        code=$(curl "$@" "$url" 2>/dev/null) || code=000
        printf '%s' "$code"
        return 0
    fi
    have wget || die "neither curl nor wget is installed"
    hdr="$out.hdr"
    set -- -q -S -T 60 -O "$out"
    if [ -n "$cacert" ]; then set -- "$@" --ca-certificate="$cacert"; fi
    if [ -n "$etag" ]; then set -- "$@" --header="If-None-Match: $etag"; fi
    if wget "$@" "$url" 2> "$hdr"; then code=200
    elif grep -q 'HTTP/[0-9.]* 304' "$hdr"; then code=304
    else code=$(sed -n 's/.*HTTP\/[0-9.]* \([0-9][0-9][0-9]\).*/\1/p' "$hdr" | tail -n 1)
    fi
    rm -f "$hdr"
    printf '%s' "${code:-000}"
}

# http_post URL BODY_FILE OUT: a JSON body, a text/plain answer; prints the status (000: no answer)
http_post() {
    url=$1 body=$2 out=$3
    cacert=$(conf_get CA_BUNDLE)
    if have curl; then
        set -- -sS --max-time 60 -o "$out" -w '%{http_code}' -X POST -H 'Content-Type: application/json' \
            -H 'Accept: text/plain' --data-binary "@$body"
        if [ -n "$cacert" ]; then set -- "$@" --cacert "$cacert"; fi
        code=$(curl "$@" "$url" 2>/dev/null) || code=000
        printf '%s' "$code"
        return 0
    fi
    have wget || die "neither curl nor wget is installed"
    hdr="$out.hdr"
    set -- -q -S -T 60 -O "$out" --header='Content-Type: application/json' --header='Accept: text/plain' \
        --post-file="$body"
    if [ -n "$cacert" ]; then set -- "$@" --ca-certificate="$cacert"; fi
    wget "$@" "$url" 2> "$hdr" || true
    code=$(sed -n 's/.*HTTP\/[0-9.]* \([0-9][0-9][0-9]\).*/\1/p' "$hdr" | tail -n 1)
    rm -f "$hdr"
    printf '%s' "${code:-000}"
}
field() { sed -n "s/^$1=//p" "$2" | head -n 1; }

# --- sshd
sshd_bin() {
    if have sshd; then command -v sshd
    elif [ -x /usr/sbin/sshd ]; then printf '%s' /usr/sbin/sshd
    else die "sshd not found"
    fi
}
sshd_test() { "$(sshd_bin)" -t -f "$SSHD_CONFIG"; }

# sshd reads its configuration again; only when the configuration test passes
reload_sshd() {
    if ! sshd_test; then log "sshd -t failed: sshd not reloaded"; return 1; fi
    pidfile=$(conf_get SSHD_PIDFILE)
    if [ -n "$pidfile" ]; then kill -HUP "$(cat "$pidfile")" && return 0; fi
    if have systemctl && [ -d /run/systemd/system ]; then
        for unit in ssh sshd; do
            if systemctl is-active --quiet "$unit.service"; then systemctl reload "$unit.service" && return 0; fi
        done
        # Socket activated: every connection starts an sshd that reads the files anew
        if systemctl is-active --quiet ssh.socket; then return 0; fi
    fi
    if have rc-service && rc-service sshd reload >/dev/null 2>&1; then return 0; fi
    if have service && { service ssh reload >/dev/null 2>&1 || service sshd reload >/dev/null 2>&1; }; then return 0; fi
    for pidfile in /run/sshd.pid /var/run/sshd.pid; do
        if [ -s "$pidfile" ] && kill -HUP "$(cat "$pidfile")" 2>/dev/null; then return 0; fi
    done
    log "could not reload sshd: reload it yourself"
    return 1
}

dropin_included() {
    [ -d "$DROPIN_DIR" ] && grep -Eiq '^[[:space:]]*Include[[:space:]].*sshd_config\.d/\*\.conf' "$SSHD_CONFIG"
}

# DEST takes the content of SRC in one rename, mode and owner kept: sshd never reads half a file
replace_file() {
    if [ -L "$2" ]; then cat "$1" > "$2"; return 0; fi
    cp -p "$2" "$2.ucm-new"
    cat "$1" > "$2.ucm-new"
    mv -f "$2.ucm-new" "$2"
}

strip_block() { # FILE: its content without the managed block
    awk -v b="$BEGIN_MARK" -v e="$END_MARK" '$0 == b { skip = 1; next } skip && $0 == e { skip = 0; next } !skip' "$1"
}

# The directives the configuration asks for, in a drop-in when sshd_config includes them, else
# in a block at the top of sshd_config (before any Match). Restored when sshd -t refuses them.
apply_sshd_config() {
    [ -f "$SSHD_CONFIG" ] || die "$SSHD_CONFIG not found"
    lines=""
    if [ -n "$(conf_get KRL_CA)" ]; then lines="RevokedKeys $KRL_FILE"; fi
    # Shell variables are global: this one is named after its function
    sshd_host_cert=$(conf_get HOST_CERT)
    if [ -n "$sshd_host_cert" ]; then
        if [ -n "$lines" ]; then lines="$lines
HostCertificate $sshd_host_cert"; else lines="HostCertificate $sshd_host_cert"; fi
    fi
    backup="$CONF_DIR/sshd_config.before-agent"
    cp -p "$SSHD_CONFIG" "$backup.$$"
    if [ -f "$DROPIN" ]; then cp -p "$DROPIN" "$backup.dropin.$$"; fi
    stripped="$CONF_DIR/.sshd_config.$$"
    strip_block "$SSHD_CONFIG" > "$stripped"
    if dropin_included; then
        if [ -n "$lines" ]; then
            printf '%s\n%s\n%s\n' "$BEGIN_MARK" "$lines" "$END_MARK" > "$DROPIN.tmp"
            chmod 644 "$DROPIN.tmp"
            mv -f "$DROPIN.tmp" "$DROPIN"
        else
            rm -f "$DROPIN"
        fi
        replace_file "$stripped" "$SSHD_CONFIG"
    elif [ -n "$lines" ]; then
        { printf '%s\n%s\n%s\n' "$BEGIN_MARK" "$lines" "$END_MARK"; cat "$stripped"; } > "$stripped.new"
        replace_file "$stripped.new" "$SSHD_CONFIG"
        rm -f "$stripped.new"
    else
        replace_file "$stripped" "$SSHD_CONFIG"
    fi
    rm -f "$stripped"
    if ! sshd_test; then
        replace_file "$backup.$$" "$SSHD_CONFIG"
        if [ -f "$backup.dropin.$$" ]; then mv -f "$backup.dropin.$$" "$DROPIN"; else rm -f "$DROPIN"; fi
        rm -f "$backup.$$"
        die "sshd -t refused the new settings: sshd_config restored"
    fi
    rm -f "$backup.$$" "$backup.dropin.$$"
    if [ -n "$(conf_get KRL_CA)" ]; then
        effective=$("$(sshd_bin)" -T -f "$SSHD_CONFIG" 2>/dev/null | sed -n 's/^revokedkeys //p' || true)
        if [ -n "$effective" ] && [ "$effective" != "$KRL_FILE" ]; then
            log "warning: sshd uses RevokedKeys $effective, set elsewhere before this agent's: remove it"
        fi
    fi
}

# --- KRL (PROTOCOL.krl): magic "SSHKRL\n\0", format version, then the 64-bit KRL version
krl_version() {
    v=0
    for b in $(od -An -tu1 -j12 -N8 "$1"); do v=$((v * 256 + b)); done
    printf '%s' "$v"
}
krl_valid() {
    [ -s "$1" ] && [ "$(dd if="$1" bs=6 count=1 2>/dev/null)" = "SSHKRL" ] || return 1
    probe=""
    for key in "$SSH_DIR"/ssh_host_*_key.pub; do
        if [ -f "$key" ]; then probe=$key; break; fi
    done
    if [ -n "$probe" ]; then
        # 0: the probe key is not revoked, 1: it is; anything else: the KRL does not parse
        rc=0; ssh-keygen -Q -f "$1" "$probe" >/dev/null 2>&1 || rc=$?
        [ "$rc" -eq 0 ] || [ "$rc" -eq 1 ]
    else
        ssh-keygen -Q -l -f "$1" >/dev/null 2>&1
    fi
}

sync_krl() {
    ca=$(conf_get KRL_CA)
    [ -n "$ca" ] || return 0
    url="$(conf_get UCM_URL)/ssh/krl/$ca"
    current=""
    if [ -s "$KRL_FILE" ]; then current=$(krl_version "$KRL_FILE"); fi
    etag=""
    if [ -n "$current" ]; then etag="\"$current\""; fi
    tmp="$CONF_DIR/.revoked_keys.$$"
    code=$(http_get "$url" "$tmp" "$etag")
    case "$code" in
        304) rm -f "$tmp"; return 0 ;;
        200) ;;
        *) rm -f "$tmp"; log "KRL download failed (HTTP $code): the installed KRL stays"; return 1 ;;
    esac
    if ! krl_valid "$tmp"; then rm -f "$tmp"; log "the downloaded KRL is not valid: the installed KRL stays"; return 1; fi
    new=$(krl_version "$tmp")
    if [ -n "$current" ] && [ "$new" -le "$current" ]; then
        rm -f "$tmp"
        if [ "$new" -lt "$current" ]; then log "refused KRL version $new, older than the installed $current"; return 1; fi
        return 0
    fi
    chmod 644 "$tmp"
    mv -f "$tmp" "$KRL_FILE"
    log "KRL version $new installed"
    CHANGED=1
}

# --- scheduler: a systemd timer, else cron
install_scheduler() {
    interval=$(conf_get INTERVAL)
    if [ -n "${UCM_AGENT_NO_SCHEDULER:-}" ]; then return 0; fi
    if have systemctl && [ -d /run/systemd/system ]; then
        printf '%s\n' '[Unit]' 'Description=UCM SSH agent: KRL and host certificate' 'After=network-online.target' \
            '' '[Service]' 'Type=oneshot' "ExecStart=$AGENT sync" > "$UNIT_DIR/ucm-ssh-agent.service"
        printf '%s\n' '[Unit]' 'Description=Run the UCM SSH agent' '' '[Timer]' 'OnBootSec=2min' \
            "OnUnitActiveSec=${interval}min" 'RandomizedDelaySec=60' 'Persistent=true' '' \
            '[Install]' 'WantedBy=timers.target' > "$UNIT_DIR/ucm-ssh-agent.timer"
        systemctl daemon-reload
        systemctl enable --now ucm-ssh-agent.timer >/dev/null 2>&1
        log "systemd timer installed: every $interval minutes"
    elif [ -d "$ROOT/etc/cron.d" ]; then
        printf '%s\n' "*/$interval * * * * root $AGENT sync >/dev/null 2>&1" > "$CRON_FILE"
        chmod 644 "$CRON_FILE"
        log "cron job installed: every $interval minutes"
    else
        log "no systemd and no /etc/cron.d: run '$AGENT sync' every $interval minutes yourself"
    fi
}
remove_scheduler() {
    if have systemctl && [ -f "$UNIT_DIR/ucm-ssh-agent.timer" ]; then
        systemctl disable --now ucm-ssh-agent.timer >/dev/null 2>&1 || true
    fi
    rm -f "$UNIT_DIR/ucm-ssh-agent.timer" "$UNIT_DIR/ucm-ssh-agent.service" "$CRON_FILE"
    if have systemctl && [ -d /run/systemd/system ]; then systemctl daemon-reload || true; fi
}

# --- commands
cmd_install_krl() { # REFID: the KRL is in place before sshd is told to read it
    case "$1" in *[!A-Za-z0-9-]*|'') die "invalid CA reference" ;; esac
    previous=$(conf_get KRL_CA)
    if [ -n "$previous" ] && [ "$previous" != "$1" ]; then
        log "this server followed the KRL of CA $previous: it now follows $1 (sshd reads one KRL)"
        rm -f "$KRL_FILE"
    fi
    conf_set KRL_CA "$1"
    if ! sync_krl || [ ! -s "$KRL_FILE" ]; then
        conf_set KRL_CA "$previous"
        die "the KRL could not be installed: sshd settings left unchanged"
    fi
    apply_sshd_config
    reload_sshd || true
}

# The host key to certify: UCM_HOST_KEY, else the first of Ed25519, ECDSA, RSA
host_key() {
    if [ -n "${UCM_HOST_KEY:-}" ]; then printf '%s' "$UCM_HOST_KEY"; return 0; fi
    for type in ed25519 ecdsa rsa; do
        if [ -f "$SSH_DIR/ssh_host_${type}_key.pub" ]; then printf '%s' "$SSH_DIR/ssh_host_${type}_key"; return 0; fi
    done
    die "no host key in $SSH_DIR"
}

# install_cert TEXT KEY: the certificate checked to certify KEY, then swapped in atomically
install_cert() {
    dest="$2-cert.pub"
    tmp="$CONF_DIR/.host-cert.$$"
    printf '%s\n' "$1" > "$tmp"
    certified=$(ssh-keygen -L -f "$tmp" 2>/dev/null | sed -n 's/^[[:space:]]*Public key: [^ ]* //p' | head -n 1)
    expected=$(ssh-keygen -l -f "$2.pub" 2>/dev/null | awk '{ print $2 }')
    if [ -z "$certified" ] || [ "$certified" != "$expected" ]; then
        rm -f "$tmp"
        log "the certificate UCM sent does not certify $2.pub: not installed"
        return 1
    fi
    # The file found there before the agent's first certificate comes back at uninstall
    if [ -f "$dest" ] && [ -z "$(conf_get HOST_CERT)" ] && [ ! -f "$CONF_DIR/host-cert.before-agent" ]; then
        cp -p "$dest" "$CONF_DIR/host-cert.before-agent"
    fi
    chmod 644 "$tmp"
    mv -f "$tmp" "$dest"
}

cmd_enroll() { # REFID [NAME...]
    refid=${1:-}
    case "$refid" in *[!A-Za-z0-9-]*|'') die "invalid CA reference" ;; esac
    shift
    token=${UCM_ENROLL_TOKEN:-}
    case "$token" in ucmh_*) ;; *) die "set UCM_ENROLL_TOKEN to the token shown in UCM" ;; esac
    case "$token" in *[!A-Za-z0-9_-]*) die "invalid enrollment token" ;; esac
    key=$(host_key)
    pub=$(awk 'NR == 1 { print $1 " " $2 }' "$key.pub")
    case "$pub" in *[!A-Za-z0-9+/=@.\ -]*|' ') die "unreadable host key $key.pub" ;; esac
    names=""
    for name in "$@"; do
        case "$name" in *[!A-Za-z0-9._:-]*|'') die "invalid host name: $name" ;; esac
        names="$names${names:+,}\"$name\""
    done
    mkdir -p "$CONF_DIR"
    body="$CONF_DIR/.enroll.$$"
    out="$CONF_DIR/.enroll-answer.$$"
    (umask 077; printf '{"token":"%s","public_key":"%s"%s}' "$token" "$pub" \
        "${names:+,\"principals\":[$names]}" > "$body")
    code=$(http_post "$(conf_get UCM_URL)/ssh/enroll/$refid" "$body" "$out")
    rm -f "$body"
    if [ "$code" != 201 ]; then
        reason=$(field error "$out" 2>/dev/null || true)
        rm -f "$out"
        die "enrollment refused (HTTP $code)${reason:+: $reason}"
    fi
    cert=$(field certificate "$out")
    host=$(field host_refid "$out")
    rm -f "$out"
    case "$host" in *[!A-Za-z0-9-]*|'') die "UCM answered no host reference" ;; esac
    install_cert "$cert" "$key" || exit 1
    conf_set HOST_CA "$refid"
    conf_set HOST_REFID "$host"
    conf_set HOST_KEY "$key"
    conf_set HOST_CERT "$key-cert.pub"
    apply_sshd_config
    reload_sshd || true
    log "enrolled: sshd presents $key-cert.pub"
}

cmd_sync() {
    status=0 CHANGED=""
    sync_krl || status=1
    if [ -n "$CHANGED" ]; then reload_sshd || true; fi
    return $status
}

cmd_status() {
    printf 'UCM: %s\n' "$(conf_get UCM_URL)"
    ca=$(conf_get KRL_CA)
    if [ -n "$ca" ] && [ -s "$KRL_FILE" ]; then
        printf 'KRL: CA %s, version %s, %s\n' "$ca" "$(krl_version "$KRL_FILE")" "$KRL_FILE"
    else
        printf 'KRL: none\n'
    fi
    host=$(conf_get HOST_REFID)
    if [ -n "$host" ]; then
        printf 'Host: %s (CA %s), certificate %s\n' "$host" "$(conf_get HOST_CA)" "$(conf_get HOST_CERT)"
        ssh-keygen -L -f "$(conf_get HOST_CERT)" 2>/dev/null | sed -n 's/^[[:space:]]*Valid: /Valid: /p'
    else
        printf 'Host: not enrolled\n'
    fi
    printf 'Interval: %s minutes\n' "$(conf_get INTERVAL)"
}

cmd_uninstall() {
    remove_scheduler
    installed_cert=$(conf_get HOST_CERT)
    conf_set KRL_CA ""
    conf_set HOST_CERT ""
    if [ -f "$SSHD_CONFIG" ]; then apply_sshd_config; reload_sshd || true; fi
    if [ -n "$installed_cert" ]; then
        if [ -f "$CONF_DIR/host-cert.before-agent" ]; then mv -f "$CONF_DIR/host-cert.before-agent" "$installed_cert"
        else rm -f "$installed_cert"
        fi
    fi
    rm -f "$KRL_FILE" "$CONF" "$CONF_DIR"/sshd_config.before-agent.*
    rmdir "$CONF_DIR" 2>/dev/null || true
    rm -f "$AGENT"
    log "uninstalled"
}

main() {
    if [ -z "$ROOT" ] && [ "$(id -u)" -ne 0 ]; then die "run as root"; fi
    command=${1:-sync}
    [ $# -gt 0 ] && shift
    case "$command" in
        install-krl) cmd_install_krl "$@" ;;
        enroll) cmd_enroll "$@" ;;
        install-scheduler) install_scheduler ;;
        sync) cmd_sync ;;
        status) cmd_status ;;
        uninstall) cmd_uninstall ;;
        *) die "usage: ucm-ssh-agent sync|status|enroll REFID [NAME...]|uninstall" ;;
    esac
}

main "$@"
'''


def installer_script(base_url, ca):
    """The script `curl -fsSL <base_url>/ssh/setup/<refid>/agent | sudo sh` runs: it writes the
    agent, then follows the KRL of the user CA *ca*. Only the URL and the refid are embedded."""
    if not _REFID.match(ca.refid or ''):
        raise ValueError('invalid CA reference')
    return INSTALLER.replace('@@UCM_URL@@', base_url).replace('@@CA_REFID@@', ca.refid) \
        .replace('@@CA_TYPE@@', ca.ca_type).replace('@@AGENT@@', AGENT)


INSTALLER = r'''#!/bin/sh
# UCM SSH agent installer. Usage:
#   curl -fsSL @@UCM_URL@@/ssh/setup/@@CA_REFID@@/agent | sudo sh
#   ... | sudo sh -s -- --interval 15 --cacert /path/to/ucm-ca.pem
#   ... | sudo sh -s -- --uninstall
# A user CA: installs /usr/local/sbin/ucm-ssh-agent and a timer that pulls the KRL of this CA
# into RevokedKeys. A host CA: enrolls this server with a single-use token from UCM,
#   ... | sudo UCM_ENROLL_TOKEN=ucmh_... sh -s -- [--principal NAME]... [--host-key PATH]
# and sshd presents the host certificate. Running it again updates the agent; nothing in it is secret.
set -eu
UCM_URL='@@UCM_URL@@'
CA_REFID='@@CA_REFID@@'
CA_TYPE='@@CA_TYPE@@'
ROOT=${UCM_AGENT_ROOT:-}
AGENT="$ROOT/usr/local/sbin/ucm-ssh-agent"
CONF="$ROOT/etc/ssh/ucm/agent.conf"

fail() { printf '%s\n' "$*" >&2; exit 1; }

setconf() {
    [ -f "$CONF" ] || : > "$CONF"
    grep -v "^$1=" "$CONF" > "$CONF.tmp" || true
    printf '%s=%s\n' "$1" "$2" >> "$CONF.tmp"
    chmod 600 "$CONF.tmp"
    mv -f "$CONF.tmp" "$CONF"
}

# One function, read whole before it runs: a command reading stdin cannot eat the piped script
install_agent() {
    interval=15 cacert="" uninstall="" names="" token=${UCM_ENROLL_TOKEN:-} hostkey=${UCM_HOST_KEY:-}
    while [ $# -gt 0 ]; do
        case "$1" in
            --interval) [ $# -ge 2 ] || fail "--interval needs a value"; interval=$2; shift 2 ;;
            --cacert) [ $# -ge 2 ] || fail "--cacert needs a file"; cacert=$2; shift 2 ;;
            --uninstall) uninstall=1; shift ;;
            --token) [ $# -ge 2 ] || fail "--token needs a value"; token=$2; shift 2 ;;
            --principal) [ $# -ge 2 ] || fail "--principal needs a host name"
                case "$2" in *[!A-Za-z0-9._:-]*|'') fail "invalid host name: $2" ;; esac
                names="$names $2"; shift 2 ;;
            --host-key) [ $# -ge 2 ] || fail "--host-key needs a path"; hostkey=$2; shift 2 ;;
            *) fail "unknown option: $1" ;;
        esac
    done
    case "$interval" in ''|*[!0-9]*) fail "the interval is a number of minutes" ;; esac
    if [ "$interval" -lt 1 ] || [ "$interval" -gt 59 ]; then fail "the interval is 1 to 59 minutes"; fi
    if [ -z "$ROOT" ] && [ "$(id -u)" -ne 0 ]; then fail "run as root (sudo)"; fi

    if [ -n "$uninstall" ]; then
        if [ -x "$AGENT" ]; then "$AGENT" uninstall < /dev/null; return; fi
        printf 'the agent is not installed\n' >&2
        return 0
    fi
    if [ "$CA_TYPE" = host ] && [ -z "$token" ]; then
        fail "this CA signs host certificates: create an enrollment token in UCM (SSH Hosts) and pass it as UCM_ENROLL_TOKEN"
    fi
    command -v ssh-keygen >/dev/null 2>&1 || fail "ssh-keygen is required"
    command -v curl >/dev/null 2>&1 || command -v wget >/dev/null 2>&1 || fail "curl or wget is required"

    mkdir -p "$(dirname "$AGENT")" "$ROOT/etc/ssh/ucm"
    cat > "$AGENT.new" <<'UCM_SSH_AGENT_END'
@@AGENT@@UCM_SSH_AGENT_END
    chmod 755 "$AGENT.new"
    mv -f "$AGENT.new" "$AGENT"

    setconf UCM_URL "$UCM_URL"
    setconf INTERVAL "$interval"
    if [ -n "$cacert" ]; then
        [ -f "$cacert" ] || fail "no such file: $cacert"
        cp "$cacert" "$ROOT/etc/ssh/ucm/ca-bundle.pem"
        setconf CA_BUNDLE "$ROOT/etc/ssh/ucm/ca-bundle.pem"
    fi
    if [ -n "${UCM_SSHD_PIDFILE:-}" ]; then setconf SSHD_PIDFILE "$UCM_SSHD_PIDFILE"; fi

    if [ "$CA_TYPE" = host ]; then
        # The token reaches the agent in its environment, never on a command line
        # shellcheck disable=SC2086
        UCM_ENROLL_TOKEN=$token UCM_HOST_KEY=$hostkey "$AGENT" enroll "$CA_REFID" $names < /dev/null
        "$AGENT" install-scheduler < /dev/null
        printf 'UCM SSH agent installed: sshd presents a host certificate of this CA.\n'
        return 0
    fi
    "$AGENT" install-krl "$CA_REFID" < /dev/null
    "$AGENT" install-scheduler < /dev/null
    printf 'UCM SSH agent installed: sshd reads the KRL of this CA, pulled every %s minutes.\n' "$interval"
}

install_agent "$@"
'''
