"""
SSH Certificate Authorities API

CRUD endpoints for SSH CAs + public key export + KRL download.
"""

import re
import logging
from flask import Blueprint, request, g, Response

from auth.unified import require_auth
from utils.response import success_response, error_response, created_response, no_content_response
from services.ssh_ca_service import SSHCAService
from services.ssh_krl_service import SSHKRLService
from services.audit_service import AuditService
from models.ssh import SSHCertificateAuthority

logger = logging.getLogger(__name__)

bp = Blueprint('ssh_cas_v2', __name__)


@bp.route('/api/v2/ssh/cas', methods=['GET'])
@require_auth(['read:ssh'])
def list_ssh_cas():
    """List all SSH CAs with optional filtering."""
    page = max(1, request.args.get('page', 1, type=int))
    per_page = min(max(1, request.args.get('per_page', 20, type=int)), 100)
    search = request.args.get('search', '').strip()
    ca_types = request.args.getlist('type')

    query = SSHCertificateAuthority.query

    if ca_types:
        valid = [t for t in ca_types if t in SSHCertificateAuthority.VALID_CA_TYPES]
        if valid:
            query = query.filter(SSHCertificateAuthority.ca_type.in_(valid))

    if search:
        safe = search.replace('\\', '\\\\').replace('%', '\\%').replace('_', '\\_')
        query = query.filter(
            SSHCertificateAuthority.descr.ilike(f'%{safe}%', escape='\\')
        )

    query = query.order_by(SSHCertificateAuthority.created_at.desc())
    pagination = query.paginate(page=page, per_page=per_page, error_out=False)

    return success_response(
        data=[ca.to_dict() for ca in pagination.items],
        meta={
            'total': pagination.total,
            'page': page,
            'per_page': per_page,
            'total_pages': (pagination.total + per_page - 1) // per_page
        }
    )


@bp.route('/api/v2/ssh/cas/<int:ca_id>', methods=['GET'])
@require_auth(['read:ssh'])
def get_ssh_ca(ca_id):
    """Get SSH CA details."""
    ca = SSHCertificateAuthority.query.get(ca_id)
    if not ca:
        return error_response('SSH CA not found', 404)

    return success_response(data=ca.to_dict())


@bp.route('/api/v2/ssh/cas/import', methods=['POST'])
@require_auth(['write:ssh'])
def import_ssh_ca():
    """Import an existing SSH CA from a private key."""
    try:
        data = request.json or {}

        private_key = (data.get('private_key') or '').strip()
        if not private_key:
            return error_response('Private key is required', 400)
        if len(private_key) > 16384:
            return error_response('Private key data too large', 400)

        descr = (data.get('descr') or data.get('name') or '').strip()[:255]
        if not descr:
            return error_response('Description is required', 400)

        ca_type = (data.get('ca_type') or 'user').strip().lower()
        if ca_type not in ('user', 'host'):
            return error_response('Invalid CA type. Must be "user" or "host".', 400)
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        ca = SSHCAService.import_ca(
            descr=descr,
            ca_type=ca_type,
            private_key_pem=private_key,
            username=username,
            default_ttl=data.get('default_ttl'),
            max_ttl=data.get('max_ttl', 0),
            comment=data.get('comment'),
            owner_group_id=data.get('owner_group_id'),
        )

        AuditService.log_action(
            action='ssh_ca_imported',
            resource_type='ssh_ca',
            resource_id=str(ca.id),
            resource_name=ca.descr,
            details=f'SSH CA "{ca.descr}" imported ({ca_type}, {ca.key_type})',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_ca_created
            on_ssh_ca_created(ca.id, ca.descr, ca_type, username)
        except Exception:
            pass

        return created_response(
            data=ca.to_dict(),
            message='SSH CA imported successfully'
        )

    except ValueError as e:
        AuditService.log_action(
            action='ssh_ca_import_failed',
            resource_type='ssh_ca',
            details=str(e)[:200],
            success=False,
            username=g.current_user.username if hasattr(g, 'current_user') else 'system',
        )
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to import SSH CA: {e}")
        AuditService.log_action(
            action='ssh_ca_import_failed',
            resource_type='ssh_ca',
            details='Internal error during SSH CA import',
            success=False,
            username=g.current_user.username if hasattr(g, 'current_user') else 'system',
        )
        return error_response('Failed to import SSH CA', 500)


@bp.route('/api/v2/ssh/cas', methods=['POST'])
@require_auth(['write:ssh'])
def create_ssh_ca():
    """Create a new SSH CA."""
    try:
        data = request.json or {}

        descr = (data.get('descr') or data.get('name') or '').strip()
        if not descr:
            return error_response('Description is required', 400)

        ca_type = (data.get('ca_type') or 'user').strip().lower()
        key_type = (data.get('key_type') or 'ed25519').strip().lower()

        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        ca = SSHCAService.create_ca(
            descr=descr,
            ca_type=ca_type,
            key_type=key_type,
            username=username,
            default_ttl=data.get('default_ttl'),
            max_ttl=data.get('max_ttl', 0),
            default_extensions=data.get('default_extensions'),
            allowed_principals=data.get('allowed_principals'),
            comment=data.get('comment'),
            owner_group_id=data.get('owner_group_id'),
        )

        AuditService.log_action(
            action='ssh_ca_created',
            resource_type='ssh_ca',
            resource_id=str(ca.id),
            resource_name=ca.descr,
            details=f'SSH CA "{ca.descr}" created ({ca_type}, {key_type})',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_ca_created
            on_ssh_ca_created(ca.id, ca.descr, ca_type, username)
        except Exception:
            pass

        return created_response(
            data=ca.to_dict(),
            message='SSH CA created successfully'
        )

    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to create SSH CA: {e}")
        return error_response('Failed to create SSH CA', 500)


@bp.route('/api/v2/ssh/cas/<int:ca_id>', methods=['PUT'])
@require_auth(['write:ssh'])
def update_ssh_ca(ca_id):
    """Update SSH CA metadata."""
    try:
        data = request.json or {}
        username = g.current_user.username if hasattr(g, 'current_user') else 'system'

        kwargs = {}
        if 'descr' in data or 'name' in data:
            descr = (data.get('descr') or data.get('name') or '').strip()
            if descr:
                kwargs['descr'] = descr
        if 'default_ttl' in data:
            kwargs['default_ttl'] = data['default_ttl']
        if 'max_ttl' in data:
            kwargs['max_ttl'] = data['max_ttl']
        if 'comment' in data:
            kwargs['comment'] = data['comment']
        if 'owner_group_id' in data:
            kwargs['owner_group_id'] = data['owner_group_id']
        if 'default_extensions' in data:
            kwargs['default_extensions'] = data['default_extensions']
        if 'allowed_principals' in data:
            kwargs['allowed_principals'] = data['allowed_principals']

        ca = SSHCAService.update_ca(ca_id, **kwargs)

        AuditService.log_action(
            action='ssh_ca_updated',
            resource_type='ssh_ca',
            resource_id=str(ca.id),
            resource_name=ca.descr,
            details=f'SSH CA "{ca.descr}" updated',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_ca_updated
            on_ssh_ca_updated(ca.id, ca.descr, username)
        except Exception:
            pass

        return success_response(
            data=ca.to_dict(),
            message='SSH CA updated successfully'
        )

    except ValueError as e:
        return error_response(str(e), 400)
    except Exception as e:
        logger.error(f"Failed to update SSH CA {ca_id}: {e}")
        return error_response('Failed to update SSH CA', 500)


@bp.route('/api/v2/ssh/cas/<int:ca_id>', methods=['DELETE'])
@require_auth(['delete:ssh'])
def delete_ssh_ca(ca_id):
    """Delete an SSH CA."""
    ca = SSHCertificateAuthority.query.get(ca_id)
    if not ca:
        return error_response('SSH CA not found', 404)

    ca_name = ca.descr
    username = g.current_user.username if hasattr(g, 'current_user') else 'system'

    try:
        SSHCAService.delete_ca(ca_id)

        AuditService.log_action(
            action='ssh_ca_deleted',
            resource_type='ssh_ca',
            resource_id=str(ca_id),
            resource_name=ca_name,
            details=f'SSH CA "{ca_name}" deleted',
            success=True,
            username=username,
        )

        try:
            from websocket.emitters import on_ssh_ca_deleted
            on_ssh_ca_deleted(ca_id, ca_name, username)
        except Exception:
            pass

        return no_content_response()

    except ValueError as e:
        return error_response(str(e), 409)
    except Exception as e:
        logger.error(f"Failed to delete SSH CA {ca_id}: {e}")
        return error_response('Failed to delete SSH CA', 500)


@bp.route('/api/v2/ssh/cas/<int:ca_id>/public-key', methods=['GET'])
@require_auth(['read:ssh'])
def get_ssh_ca_public_key(ca_id):
    """Download the CA's public key in OpenSSH format.

    Used for sshd_config TrustedUserCAKeys or ssh_known_hosts.
    """
    try:
        pub_key = SSHCAService.get_public_key(ca_id)
        ca = SSHCertificateAuthority.query.get(ca_id)

        return Response(
            pub_key,
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'attachment; filename="ssh_ca_{re.sub(r"[^a-zA-Z0-9_.-]", "_", ca.descr)}.pub"'
            }
        )
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"Failed to export SSH CA public key: {e}")
        return error_response('Failed to export public key', 500)


@bp.route('/api/v2/ssh/cas/<int:ca_id>/setup-script', methods=['GET'])
@require_auth(['read:ssh'])
def get_ssh_ca_setup_script(ca_id):
    """Generate a distro-agnostic server setup script for SSH CA trust."""
    try:
        ca = SSHCertificateAuthority.query.get(ca_id)
        if not ca:
            return error_response('SSH CA not found', 404)

        pub_key = SSHCAService.get_public_key(ca_id)

        ca_type = request.args.get('type', '').strip().lower()
        if ca_type and ca_type not in ('user', 'host'):
            return error_response('Invalid type parameter. Must be "user" or "host"', 400)
        if not ca_type:
            ca_type = ca.ca_type

        hostname = request.args.get('hostname', '').strip()
        if hostname and not re.match(r'^[a-zA-Z0-9._-]+$', hostname):
            return error_response('Invalid hostname format', 400)

        platform = request.args.get('platform', 'unix').strip().lower()
        if platform not in ('unix', 'linux', 'macos', 'windows'):
            return error_response('Invalid platform parameter. Must be "unix" or "windows"', 400)

        script = _generate_setup_script(ca, pub_key, ca_type, hostname, platform)
        safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', ca.descr)

        if platform == 'windows':
            mimetype = 'text/x-powershell'
            filename = f'ssh_ca_setup_{safe_name}.ps1'
        else:
            mimetype = 'text/x-shellscript'
            filename = f'ssh_ca_setup_{safe_name}.sh'

        return Response(
            script,
            mimetype=mimetype,
            headers={
                'Content-Disposition': f'attachment; filename="{filename}"'
            }
        )
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"Failed to generate SSH CA setup script: {e}")
        return error_response('Failed to generate setup script', 500)


def _generate_setup_script(ca, pub_key, ca_type, hostname, platform='unix'):
    """Build a shell or PowerShell script for SSH CA trust configuration."""
    ca_label = ca.descr.replace("'", "'\\''")

    if platform == 'windows':
        # PowerShell escaping: backtick-escape backticks, escape single quotes for here-strings
        ps_key = pub_key.strip().replace('`', '``')
        ps_label = ca.descr.replace('`', '``').replace('"', '`"')
        if ca_type == 'user':
            return _user_ca_script_windows(ps_key, ps_label)
        return _host_ca_script_windows(ps_key, ps_label, hostname)

    safe_key = pub_key.strip().replace("'", "'\\''")
    if ca_type == 'user':
        return _user_ca_script(safe_key, ca_label)
    return _host_ca_script(safe_key, ca_label, hostname)


def _user_ca_script(pub_key, ca_label):
    return rf'''#!/bin/sh
# ============================================================================
# SSH User CA Trust Setup Script
# CA: {ca_label}
# Generated by UCM (Ultimate Certificate Manager)
#
# This script configures sshd to trust certificates signed by the above CA
# for user authentication (TrustedUserCAKeys).
#
# Usage:
#   sudo sh setup_script.sh              # Apply changes
#   sudo sh setup_script.sh --dry-run    # Preview without modifying
# ============================================================================

set -eu

# --- Configuration ---
CA_KEY_DIR="/etc/ssh/ssh_ca_keys"
CA_KEY_FILE="$CA_KEY_DIR/user_ca.pub"
SSHD_CONFIG="/etc/ssh/sshd_config"
PRINCIPALS_DIR="/etc/ssh/auth_principals"
DRY_RUN=false

# --- Colors ---
if [ -t 1 ]; then
    RED="\\033[0;31m"
    GREEN="\\033[0;32m"
    YELLOW="\\033[0;33m"
    BLUE="\\033[0;34m"
    BOLD="\\033[1m"
    NC="\\033[0m"
else
    RED="" GREEN="" YELLOW="" BLUE="" BOLD="" NC=""
fi

# --- Helpers ---
info()  {{ printf "%b[INFO]%b  %s\\n" "$BLUE" "$NC" "$1"; }}
ok()    {{ printf "%b[OK]%b    %s\\n" "$GREEN" "$NC" "$1"; }}
warn()  {{ printf "%b[WARN]%b  %s\\n" "$YELLOW" "$NC" "$1"; }}
err()   {{ printf "%b[ERROR]%b %s\\n" "$RED" "$NC" "$1" >&2; }}

# --- Parse arguments ---
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --help|-h)
            printf "Usage: sudo sh %s [--dry-run]\\n" "$0"
            printf "  --dry-run  Show what would be changed without modifying anything\\n"
            exit 0
            ;;
        *) err "Unknown option: $arg"; exit 1 ;;
    esac
done

# --- Root check ---
if [ "$(id -u)" -ne 0 ]; then
    err "This script must be run as root (or with sudo)."
    exit 1
fi

printf "%b========================================%b\\n" "$BOLD" "$NC"
printf "%bSSH User CA Trust Setup%b\\n" "$BOLD" "$NC"
printf "CA: %s\\n" "{ca_label}"
if [ "$DRY_RUN" = true ]; then
    printf "%b>>> DRY RUN — no changes will be made <<<%b\\n" "$YELLOW" "$NC"
fi
printf "%b========================================%b\\n\\n" "$BOLD" "$NC"

# --- Detect OS ---
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="$ID"
    OS_NAME="$PRETTY_NAME"
else
    OS_ID="unknown"
    OS_NAME="Unknown OS"
fi
info "Detected OS: $OS_NAME"

# --- Determine sshd restart command ---
detect_restart_cmd() {{
    if command -v systemctl >/dev/null 2>&1; then
        if systemctl list-unit-files sshd.service >/dev/null 2>&1; then
            echo "systemctl reload sshd"
        else
            echo "systemctl reload ssh"
        fi
    elif command -v rc-service >/dev/null 2>&1; then
        echo "rc-service sshd reload"
    elif command -v service >/dev/null 2>&1; then
        echo "service sshd reload"
    else
        echo ""
    fi
}}

RESTART_CMD=$(detect_restart_cmd)
if [ -z "$RESTART_CMD" ]; then
    warn "Could not detect sshd service manager. You will need to reload sshd manually."
fi

# --- Step 1: Create CA key directory ---
info "Creating CA key directory: $CA_KEY_DIR"
if [ "$DRY_RUN" = true ]; then
    if [ -d "$CA_KEY_DIR" ]; then
        ok "Directory already exists (no change needed)"
    else
        info "Would create: $CA_KEY_DIR"
    fi
else
    mkdir -p "$CA_KEY_DIR"
    chmod 755 "$CA_KEY_DIR"
    ok "Directory ready: $CA_KEY_DIR"
fi

# --- Step 2: Write CA public key ---
CA_PUB_KEY=\'{pub_key}\'

info "Writing CA public key to: $CA_KEY_FILE"
if [ "$DRY_RUN" = true ]; then
    if [ -f "$CA_KEY_FILE" ]; then
        EXISTING=$(cat "$CA_KEY_FILE" 2>/dev/null || echo "")
        if [ "$EXISTING" = "$CA_PUB_KEY" ]; then
            ok "Key file already contains the correct key (no change needed)"
        else
            warn "Would overwrite existing key file"
        fi
    else
        info "Would create: $CA_KEY_FILE"
    fi
else
    printf "%s\\n" "$CA_PUB_KEY" > "$CA_KEY_FILE"
    chmod 644 "$CA_KEY_FILE"
    ok "CA public key written"
fi

# --- Step 3: Back up sshd_config ---
if [ ! -f "$SSHD_CONFIG" ]; then
    err "sshd_config not found at $SSHD_CONFIG"
    exit 1
fi

BACKUP="$SSHD_CONFIG.bak.$(date +%Y%m%d%H%M%S)"
info "Backing up sshd_config to: $BACKUP"
if [ "$DRY_RUN" = true ]; then
    info "Would create backup: $BACKUP"
else
    cp "$SSHD_CONFIG" "$BACKUP"
    ok "Backup created"
fi

# --- Step 4: Add TrustedUserCAKeys directive ---
info "Checking sshd_config for TrustedUserCAKeys directive..."
if grep -qE "^\\s*TrustedUserCAKeys" "$SSHD_CONFIG" 2>/dev/null; then
    CURRENT=$(grep -E "^\\s*TrustedUserCAKeys" "$SSHD_CONFIG" | head -1)
    warn "TrustedUserCAKeys is already configured: $CURRENT"
    warn "Skipping — please verify the path is correct or update manually."
else
    if [ "$DRY_RUN" = true ]; then
        info "Would add to $SSHD_CONFIG:"
        info "  TrustedUserCAKeys $CA_KEY_FILE"
    else
        printf "\\n# SSH User CA Trust — added by UCM setup script\\nTrustedUserCAKeys %s\\n" "$CA_KEY_FILE" >> "$SSHD_CONFIG"
        ok "Added TrustedUserCAKeys directive to sshd_config"
    fi
fi

# --- Step 5: Set up AuthorizedPrincipalsFile (optional) ---
info "Setting up AuthorizedPrincipalsFile directory: $PRINCIPALS_DIR"
if [ "$DRY_RUN" = true ]; then
    if [ -d "$PRINCIPALS_DIR" ]; then
        ok "Principals directory already exists"
    else
        info "Would create: $PRINCIPALS_DIR"
    fi
else
    mkdir -p "$PRINCIPALS_DIR"
    chmod 755 "$PRINCIPALS_DIR"
    ok "Principals directory ready"
fi

if grep -qE "^\\s*AuthorizedPrincipalsFile" "$SSHD_CONFIG" 2>/dev/null; then
    CURRENT=$(grep -E "^\\s*AuthorizedPrincipalsFile" "$SSHD_CONFIG" | head -1)
    warn "AuthorizedPrincipalsFile already configured: $CURRENT"
else
    if [ "$DRY_RUN" = true ]; then
        info "Would add to $SSHD_CONFIG:"
        info "  AuthorizedPrincipalsFile $PRINCIPALS_DIR/%u"
    else
        printf "AuthorizedPrincipalsFile %s/%%u\\n" "$PRINCIPALS_DIR" >> "$SSHD_CONFIG"
        ok "Added AuthorizedPrincipalsFile directive"
    fi
fi

# --- Step 6: Validate sshd config ---
info "Validating sshd configuration..."
if command -v sshd >/dev/null 2>&1; then
    if [ "$DRY_RUN" = true ]; then
        info "Would run: sshd -t"
    else
        if sshd -t 2>/dev/null; then
            ok "sshd configuration is valid"
        else
            err "sshd configuration test failed! Restoring backup..."
            cp "$BACKUP" "$SSHD_CONFIG"
            err "Backup restored. Please check your sshd_config manually."
            exit 1
        fi
    fi
else
    warn "sshd binary not found in PATH — skipping config validation"
fi

# --- Step 7: Reload sshd ---
if [ -n "$RESTART_CMD" ]; then
    info "Reloading sshd: $RESTART_CMD"
    if [ "$DRY_RUN" = true ]; then
        info "Would run: $RESTART_CMD"
    else
        if $RESTART_CMD; then
            ok "sshd reloaded successfully"
        else
            warn "sshd reload returned non-zero. Check service status manually."
        fi
    fi
fi

# --- Done ---
printf "\\n%b========================================%b\\n" "$BOLD" "$NC"
if [ "$DRY_RUN" = true ]; then
    printf "%bDry run complete — no changes were made.%b\\n" "$YELLOW" "$NC"
else
    printf "%bSetup complete!%b\\n" "$GREEN" "$NC"
fi
printf "%b========================================%b\\n\\n" "$BOLD" "$NC"

if [ "$DRY_RUN" != true ]; then
    info "Next steps:"
    info "  1. For each user, create a principals file:"
    info "     echo \\"principal_name\\" > $PRINCIPALS_DIR/<username>"
    info "  2. Sign user keys with the CA using UCM or ssh-keygen"
    info "  3. Users can now log in with their signed certificate"
fi
'''


def _host_ca_script(pub_key, ca_label, hostname):
    hostname_display = hostname if hostname else '$(hostname -f)'
    return rf'''#!/bin/sh
# ============================================================================
# SSH Host CA Trust Setup Script
# CA: {ca_label}
# Generated by UCM (Ultimate Certificate Manager)
#
# This script configures sshd to present a host certificate signed by the
# above CA, proving the server\'s identity to connecting clients.
#
# Usage:
#   sudo sh setup_script.sh              # Apply changes
#   sudo sh setup_script.sh --dry-run    # Preview without modifying
# ============================================================================

set -eu

# --- Configuration ---
CA_KEY_DIR="/etc/ssh/ssh_ca_keys"
CA_KEY_FILE="$CA_KEY_DIR/host_ca.pub"
SSHD_CONFIG="/etc/ssh/sshd_config"
HOSTNAME="{hostname if hostname else ""}"
DRY_RUN=false

# --- Colors ---
if [ -t 1 ]; then
    RED="\\033[0;31m"
    GREEN="\\033[0;32m"
    YELLOW="\\033[0;33m"
    BLUE="\\033[0;34m"
    BOLD="\\033[1m"
    NC="\\033[0m"
else
    RED="" GREEN="" YELLOW="" BLUE="" BOLD="" NC=""
fi

# --- Helpers ---
info()  {{ printf "%b[INFO]%b  %s\\n" "$BLUE" "$NC" "$1"; }}
ok()    {{ printf "%b[OK]%b    %s\\n" "$GREEN" "$NC" "$1"; }}
warn()  {{ printf "%b[WARN]%b  %s\\n" "$YELLOW" "$NC" "$1"; }}
err()   {{ printf "%b[ERROR]%b %s\\n" "$RED" "$NC" "$1" >&2; }}

# --- Parse arguments ---
for arg in "$@"; do
    case "$arg" in
        --dry-run) DRY_RUN=true ;;
        --help|-h)
            printf "Usage: sudo sh %s [--dry-run]\\n" "$0"
            printf "  --dry-run  Show what would be changed without modifying anything\\n"
            exit 0
            ;;
        *) err "Unknown option: $arg"; exit 1 ;;
    esac
done

# --- Root check ---
if [ "$(id -u)" -ne 0 ]; then
    err "This script must be run as root (or with sudo)."
    exit 1
fi

# --- Resolve hostname ---
if [ -z "$HOSTNAME" ]; then
    HOSTNAME=$(hostname -f 2>/dev/null || hostname)
fi

printf "%b========================================%b\\n" "$BOLD" "$NC"
printf "%bSSH Host CA Trust Setup%b\\n" "$BOLD" "$NC"
printf "CA: %s\\n" "{ca_label}"
printf "Host: %s\\n" "$HOSTNAME"
if [ "$DRY_RUN" = true ]; then
    printf "%b>>> DRY RUN — no changes will be made <<<%b\\n" "$YELLOW" "$NC"
fi
printf "%b========================================%b\\n\\n" "$BOLD" "$NC"

# --- Detect OS ---
if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS_ID="$ID"
    OS_NAME="$PRETTY_NAME"
else
    OS_ID="unknown"
    OS_NAME="Unknown OS"
fi
info "Detected OS: $OS_NAME"

# --- Determine sshd restart command ---
detect_restart_cmd() {{
    if command -v systemctl >/dev/null 2>&1; then
        if systemctl list-unit-files sshd.service >/dev/null 2>&1; then
            echo "systemctl reload sshd"
        else
            echo "systemctl reload ssh"
        fi
    elif command -v rc-service >/dev/null 2>&1; then
        echo "rc-service sshd reload"
    elif command -v service >/dev/null 2>&1; then
        echo "service sshd reload"
    else
        echo ""
    fi
}}

RESTART_CMD=$(detect_restart_cmd)
if [ -z "$RESTART_CMD" ]; then
    warn "Could not detect sshd service manager. You will need to reload sshd manually."
fi

# --- Step 1: Create CA key directory ---
info "Creating CA key directory: $CA_KEY_DIR"
if [ "$DRY_RUN" = true ]; then
    if [ -d "$CA_KEY_DIR" ]; then
        ok "Directory already exists (no change needed)"
    else
        info "Would create: $CA_KEY_DIR"
    fi
else
    mkdir -p "$CA_KEY_DIR"
    chmod 755 "$CA_KEY_DIR"
    ok "Directory ready: $CA_KEY_DIR"
fi

# --- Step 2: Write CA public key ---
CA_PUB_KEY=\'{pub_key}\'

info "Writing CA public key to: $CA_KEY_FILE"
if [ "$DRY_RUN" = true ]; then
    if [ -f "$CA_KEY_FILE" ]; then
        EXISTING=$(cat "$CA_KEY_FILE" 2>/dev/null || echo "")
        if [ "$EXISTING" = "$CA_PUB_KEY" ]; then
            ok "Key file already contains the correct key (no change needed)"
        else
            warn "Would overwrite existing key file"
        fi
    else
        info "Would create: $CA_KEY_FILE"
    fi
else
    printf "%s\\n" "$CA_PUB_KEY" > "$CA_KEY_FILE"
    chmod 644 "$CA_KEY_FILE"
    ok "CA public key written"
fi

# --- Step 3: Back up sshd_config ---
if [ ! -f "$SSHD_CONFIG" ]; then
    err "sshd_config not found at $SSHD_CONFIG"
    exit 1
fi

BACKUP="$SSHD_CONFIG.bak.$(date +%Y%m%d%H%M%S)"
info "Backing up sshd_config to: $BACKUP"
if [ "$DRY_RUN" = true ]; then
    info "Would create backup: $BACKUP"
else
    cp "$SSHD_CONFIG" "$BACKUP"
    ok "Backup created"
fi

# --- Step 4: Sign the host key ---
# Find available host keys
HOST_KEY=""
for kt in ed25519 ecdsa rsa; do
    if [ -f "/etc/ssh/ssh_host_${{kt}}_key.pub" ]; then
        HOST_KEY="/etc/ssh/ssh_host_${{kt}}_key"
        break
    fi
done

if [ -z "$HOST_KEY" ]; then
    err "No SSH host key found in /etc/ssh/"
    exit 1
fi

CERT_FILE="${{HOST_KEY}}-cert.pub"
info "Found host key: $HOST_KEY"

if [ -f "$CERT_FILE" ]; then
    warn "Host certificate already exists: $CERT_FILE"
    warn "If you want to re-sign, remove it first and re-run this script."
else
    printf "\\n"
    warn "Host key signing requires the CA private key, which is managed by UCM."
    info "To sign the host key, use one of these methods:"
    printf "\\n"
    info "  Option A: Sign via UCM web interface"
    info "    1. Copy the host public key: $HOST_KEY.pub"
    info "    2. Go to UCM > SSH > Certificates > Sign Host Key"
    info "    3. Upload the public key and specify principals: $HOSTNAME"
    info "    4. Download the signed certificate"
    info "    5. Place it at: $CERT_FILE"
    printf "\\n"
    info "  Option B: Sign via UCM API"
    info "    curl -X POST https://<ucm-server>/api/v2/ssh/certificates/sign \\\\"
    info "      -H 'Content-Type: application/json' \\\\"
    info "      -d '{{\"ca_id\": {ca_label}, \"cert_type\": \"host\", ...}}'"
    printf "\\n"
fi

# --- Step 5: Add HostCertificate directive ---
info "Checking sshd_config for HostCertificate directive..."
if grep -qE "^\\s*HostCertificate" "$SSHD_CONFIG" 2>/dev/null; then
    CURRENT=$(grep -E "^\\s*HostCertificate" "$SSHD_CONFIG" | head -1)
    warn "HostCertificate is already configured: $CURRENT"
    warn "Skipping — please verify the path is correct or update manually."
else
    if [ "$DRY_RUN" = true ]; then
        info "Would add to $SSHD_CONFIG:"
        info "  HostCertificate $CERT_FILE"
    else
        printf "\\n# SSH Host Certificate — added by UCM setup script\\nHostCertificate %s\\n" "$CERT_FILE" >> "$SSHD_CONFIG"
        ok "Added HostCertificate directive to sshd_config"
    fi
fi

# --- Step 6: Validate sshd config ---
info "Validating sshd configuration..."
if command -v sshd >/dev/null 2>&1; then
    if [ "$DRY_RUN" = true ]; then
        info "Would run: sshd -t"
    else
        if sshd -t 2>/dev/null; then
            ok "sshd configuration is valid"
        else
            err "sshd configuration test failed! Restoring backup..."
            cp "$BACKUP" "$SSHD_CONFIG"
            err "Backup restored. Please check your sshd_config manually."
            exit 1
        fi
    fi
else
    warn "sshd binary not found in PATH — skipping config validation"
fi

# --- Step 7: Reload sshd ---
if [ -n "$RESTART_CMD" ]; then
    info "Reloading sshd: $RESTART_CMD"
    if [ "$DRY_RUN" = true ]; then
        info "Would run: $RESTART_CMD"
    else
        if [ -f "$CERT_FILE" ]; then
            if $RESTART_CMD; then
                ok "sshd reloaded successfully"
            else
                warn "sshd reload returned non-zero. Check service status manually."
            fi
        else
            warn "Skipping sshd reload — host certificate not yet present."
            warn "Sign the host key first, then reload sshd manually."
        fi
    fi
fi

# --- Done ---
printf "\\n%b========================================%b\\n" "$BOLD" "$NC"
if [ "$DRY_RUN" = true ]; then
    printf "%bDry run complete — no changes were made.%b\\n" "$YELLOW" "$NC"
else
    printf "%bSetup complete!%b\\n" "$GREEN" "$NC"
fi
printf "%b========================================%b\\n\\n" "$BOLD" "$NC"

if [ "$DRY_RUN" != true ]; then
    info "Next steps:"
    if [ ! -f "$CERT_FILE" ]; then
        info "  1. Sign the host key via UCM (see instructions above)"
        info "  2. Place the signed certificate at: $CERT_FILE"
        info "  3. Reload sshd: $RESTART_CMD"
    fi
    info "  Clients should add to their ~/.ssh/known_hosts or ssh_known_hosts:"
    info "    @cert-authority * $(cat $CA_KEY_FILE 2>/dev/null || echo '<CA public key>')"
fi
'''


def _user_ca_script_windows(pub_key, ca_label):
    # PowerShell single-quoted strings preserve everything literally except '' (escaped quote).
    # Escape any single quote in the public key for safety.
    ps_pub_key = pub_key.replace("'", "''")
    ps_label = ca_label.replace("'", "''")
    return rf'''<#
.SYNOPSIS
    SSH User CA Trust Setup Script (Windows OpenSSH Server)
    CA: {ca_label}
    Generated by UCM (Ultimate Certificate Manager)

.DESCRIPTION
    Configures the Windows OpenSSH Server (sshd) to trust user certificates
    signed by the above CA. Writes the CA public key to ProgramData\\ssh\\ssh_ca_keys
    and adds TrustedUserCAKeys + AuthorizedPrincipalsFile directives to sshd_config.

    Run from an elevated PowerShell prompt.

.PARAMETER DryRun
    Preview what would change without modifying any file or service.

.PARAMETER NonInteractive
    Skip all prompts (OpenSSH install, end pause). Use in CI/automation.

.PARAMETER NoPause
    Do not pause at the end (default is to pause so the window stays open).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\\ssh_ca_setup.ps1
    powershell -ExecutionPolicy Bypass -File .\\ssh_ca_setup.ps1 -DryRun
    powershell -ExecutionPolicy Bypass -File .\\ssh_ca_setup.ps1 -NonInteractive -NoPause
#>

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$NonInteractive,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'

# --- Helpers ---
function Write-Info  ($msg) {{ Write-Host "[INFO]  $msg" -ForegroundColor Cyan }}
function Write-Ok    ($msg) {{ Write-Host "[OK]    $msg" -ForegroundColor Green }}
function Write-Warn2 ($msg) {{ Write-Host "[WARN]  $msg" -ForegroundColor Yellow }}
function Write-Err   ($msg) {{ Write-Host "[ERROR] $msg" -ForegroundColor Red }}

function Pause-IfInteractive {{
    param([string]$Message = 'Press Enter to close this window...')
    if ($NoPause -or $NonInteractive) {{ return }}
    try {{ Read-Host -Prompt $Message | Out-Null }} catch {{ Start-Sleep -Seconds 30 }}
}}

# --- Transcript log (always-on so output survives even if window closes) ---
$LogFile = Join-Path $env:TEMP ("ucm_ssh_user_ca_setup_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + ".log")
try {{ Start-Transcript -Path $LogFile -Force | Out-Null }} catch {{ }}
Write-Host "Log file: $LogFile" -ForegroundColor DarkGray

$ScriptFailed = $false
try {{

# --- Configuration ---
$SshDir         = Join-Path $env:ProgramData 'ssh'
$CaKeyDir       = Join-Path $SshDir 'ssh_ca_keys'
$CaKeyFile      = Join-Path $CaKeyDir 'user_ca.pub'
$SshdConfig     = Join-Path $SshDir 'sshd_config'
$PrincipalsDir  = Join-Path $SshDir 'auth_principals'

# --- Admin check ---
$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {{
    Write-Err "This script must be run as Administrator."
    Write-Info "Right-click PowerShell -> Run as Administrator, then re-run this script."
    throw "Not running as Administrator"
}}

Write-Host "========================================" -ForegroundColor White
Write-Host "SSH User CA Trust Setup (Windows)"      -ForegroundColor White
Write-Host "CA: {ca_label}"
if ($DryRun) {{
    Write-Host ">>> DRY RUN - no changes will be made <<<" -ForegroundColor Yellow
}}
Write-Host "========================================" -ForegroundColor White
Write-Host ""

# --- Pre-flight: detect existing OpenSSH Server install (FoD or winget) ---
$sshdSvc = Get-Service -Name sshd -ErrorAction SilentlyContinue
$fodInstalled = $false
$wingetInstalled = $false
try {{
    $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' -ErrorAction SilentlyContinue
    if ($cap -and $cap.State -eq 'Installed') {{ $fodInstalled = $true }}
}} catch {{ }}
$wingetSshdPath = Join-Path $env:ProgramFiles 'OpenSSH\sshd.exe'
if (Test-Path $wingetSshdPath) {{ $wingetInstalled = $true }}

if ($fodInstalled) {{
    Write-Info "Detected OpenSSH Server install: Windows Features-on-Demand"
    Write-Info "  Binary: $env:WINDIR\System32\OpenSSH\sshd.exe"
}}
if ($wingetInstalled) {{
    Write-Info "Detected OpenSSH Server install: winget / standalone"
    Write-Info "  Binary: $wingetSshdPath"
}}
Write-Info "CA public key will be installed to: $CaKeyFile"
Write-Info "sshd_config will be updated at:    $SshdConfig"

if (-not ($fodInstalled -or $wingetInstalled -or $sshdSvc)) {{
    Write-Warn2 "OpenSSH Server is not installed (neither FoD nor winget detected)."
    $doInstall = $false
    if ($DryRun) {{
        Write-Info "Would offer to install OpenSSH.Server via Features-on-Demand (skipped in -DryRun)."
    }} elseif ($NonInteractive) {{
        Write-Err "OpenSSH Server is missing and -NonInteractive was supplied."
        Write-Info "Install manually with one of:"
        Write-Info "  Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0"
        Write-Info "  winget install Microsoft.OpenSSH.Beta"
        Write-Info "Then: Set-Service -Name sshd -StartupType 'Automatic'; Start-Service sshd"
        throw "OpenSSH Server missing"
    }} else {{
        $resp = Read-Host "Install OpenSSH Server via Features-on-Demand now? [Y/n]"
        if ($resp -eq '' -or $resp -match '^[Yy]') {{ $doInstall = $true }}
    }}
    if ($doInstall) {{
        Write-Info "Installing OpenSSH.Server via Add-WindowsCapability (this may take 1-2 minutes)..."
        try {{
            Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 -ErrorAction Stop | Out-Null
        }} catch {{
            $errMsg = $_.Exception.Message
            Write-Err "Add-WindowsCapability failed: $errMsg"
            Write-Host ""
            Write-Host "---- Diagnostic ----" -ForegroundColor Yellow
            if ($errMsg -match '0x8024500c|WU_E_PT_WMT_MISSING') {{
                Write-Host "Cause: 0x8024500c (WU_E_PT_WMT_MISSING)" -ForegroundColor Yellow
                Write-Host "  This machine is configured to use WSUS (group policy), but the WSUS server"
                Write-Host "  does not host the OpenSSH Features-on-Demand source, so Windows refuses to"
                Write-Host "  download it from Microsoft Update."
            }} elseif ($errMsg -match '0x800f0954') {{
                Write-Host "Cause: 0x800f0954 (CBS_E_INVALID_WINDOWS_UPDATE_COUNT_WSUS)" -ForegroundColor Yellow
                Write-Host "  Group policy forbids reaching Microsoft Update for Features-on-Demand."
            }} elseif ($errMsg -match '0x80240438|0x8024402c|0x80072ee2|0x80072efd') {{
                Write-Host "Cause: Windows Update / WSUS connectivity error ($errMsg)" -ForegroundColor Yellow
                Write-Host "  The Windows Update client cannot reach its configured update source."
            }} else {{
                Write-Host "Cause: see error message above." -ForegroundColor Yellow
            }}
            $regAU = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
            $useWUServer = (Get-ItemProperty -Path $regAU -Name UseWUServer -ErrorAction SilentlyContinue).UseWUServer
            $wuServer = (Get-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate' -Name WUServer -ErrorAction SilentlyContinue).WUServer
            if ($useWUServer -eq 1) {{
                Write-Host ("  Detected WSUS policy: UseWUServer=1, WUServer={0}" -f $wuServer)
            }} else {{
                Write-Host "  No WSUS policy detected (UseWUServer != 1)."
            }}
            Write-Host ""
            Write-Host "Resolution options (ask your Windows / AD team — do NOT bypass policy yourself):" -ForegroundColor Cyan
            Write-Host "  1. Ask the WSUS admin to approve the OpenSSH FoD package, OR enable the policy"
            Write-Host "     'Specify settings for optional component installation and component repair'"
            Write-Host "     with 'Download repair content ... directly from Windows Update' enabled"
            Write-Host "     (Computer Config > Admin Templates > System)."
            Write-Host "  2. Install offline from a Features-on-Demand ISO matching this Windows build:"
            Write-Host "     Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 -Source <FoD-ISO>\LanguagesAndOptionalFeatures"
            Write-Host "  3. Install OpenSSH Server manually via Settings > Apps > Optional features."
            Write-Host "Re-run this script once OpenSSH Server is installed and running."
            Write-Host "--------------------" -ForegroundColor Yellow
            throw
        }}
        Set-Service -Name sshd -StartupType 'Automatic'
        Start-Service sshd
        if (-not (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue)) {{
            try {{
                New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' `
                    -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
                Write-Ok "Firewall rule added (TCP/22 inbound)"
            }} catch {{
                Write-Warn2 "Could not create firewall rule: $_"
            }}
        }}
        $sshdSvc = Get-Service -Name sshd
        Write-Ok "OpenSSH Server installed and started"
    }} elseif (-not $DryRun) {{
        throw "OpenSSH Server is required. Install it and re-run this script."
    }}
}} elseif ($sshdSvc) {{
    Write-Info "sshd service detected (status: $($sshdSvc.Status))"
}} else {{
    Write-Warn2 "OpenSSH binaries detected but sshd service is not registered."
    Write-Info "Run: Set-Service -Name sshd -StartupType 'Automatic'; Start-Service sshd"
}}

# --- Step 1: Create CA key directory ---
Write-Info "Creating CA key directory: $CaKeyDir"
if ($DryRun) {{
    if (Test-Path $CaKeyDir) {{ Write-Ok "Directory already exists" }} else {{ Write-Info "Would create: $CaKeyDir" }}
}} else {{
    New-Item -ItemType Directory -Path $CaKeyDir -Force | Out-Null
    Write-Ok "Directory ready: $CaKeyDir"
}}

# --- Step 2: Write CA public key ---
$CaPubKey = @'
{ps_pub_key}
'@

Write-Info "Writing CA public key to: $CaKeyFile"
if ($DryRun) {{
    if (Test-Path $CaKeyFile) {{
        $existing = Get-Content $CaKeyFile -Raw -ErrorAction SilentlyContinue
        if ($existing.Trim() -eq $CaPubKey.Trim()) {{
            Write-Ok "Key file already contains the correct key"
        }} else {{
            Write-Warn2 "Would overwrite existing key file"
        }}
    }} else {{
        Write-Info "Would create: $CaKeyFile"
    }}
}} else {{
    Set-Content -Path $CaKeyFile -Value $CaPubKey -Encoding ASCII -NoNewline:$false
    # Lock down ACL: SYSTEM + Administrators full, no inheritance, no Everyone
    $acl = Get-Acl $CaKeyFile
    $acl.SetAccessRuleProtection($true, $false)
    $acl.Access | ForEach-Object {{ [void]$acl.RemoveAccessRule($_) }}
    $rules = @(
        New-Object System.Security.AccessControl.FileSystemAccessRule('NT AUTHORITY\\SYSTEM','FullControl','Allow'),
        New-Object System.Security.AccessControl.FileSystemAccessRule('BUILTIN\\Administrators','FullControl','Allow')
    )
    foreach ($r in $rules) {{ $acl.AddAccessRule($r) }}
    Set-Acl -Path $CaKeyFile -AclObject $acl
    Write-Ok "CA public key written"
}}

# --- Step 3: Back up sshd_config ---
if (-not (Test-Path $SshdConfig)) {{
    Write-Err "sshd_config not found at $SshdConfig"
    exit 1
}}
$backup = "$SshdConfig.bak.$(Get-Date -Format 'yyyyMMddHHmmss')"
Write-Info "Backing up sshd_config to: $backup"
if ($DryRun) {{
    Write-Info "Would create backup: $backup"
}} else {{
    Copy-Item -Path $SshdConfig -Destination $backup
    Write-Ok "Backup created"
}}

# --- Step 4: Add TrustedUserCAKeys directive ---
Write-Info "Checking sshd_config for TrustedUserCAKeys directive..."
$existingConfig = Get-Content $SshdConfig -Raw
if ($existingConfig -match '(?m)^\\s*TrustedUserCAKeys\\b') {{
    Write-Warn2 "TrustedUserCAKeys is already configured. Skipping - verify path is correct."
}} else {{
    if ($DryRun) {{
        Write-Info "Would append to ${{SshdConfig}}:"
        Write-Info "  TrustedUserCAKeys $CaKeyFile"
    }} else {{
        Add-Content -Path $SshdConfig -Value ""
        Add-Content -Path $SshdConfig -Value "# SSH User CA Trust - added by UCM setup script"
        Add-Content -Path $SshdConfig -Value "TrustedUserCAKeys $CaKeyFile"
        Write-Ok "Added TrustedUserCAKeys directive"
    }}
}}

# --- Step 5: AuthorizedPrincipalsFile directory ---
Write-Info "Setting up AuthorizedPrincipalsFile directory: $PrincipalsDir"
if (-not $DryRun) {{
    New-Item -ItemType Directory -Path $PrincipalsDir -Force | Out-Null
    Write-Ok "Principals directory ready"
}}

if ($existingConfig -match '(?m)^\\s*AuthorizedPrincipalsFile\\b') {{
    Write-Warn2 "AuthorizedPrincipalsFile already configured. Skipping."
}} else {{
    if ($DryRun) {{
        Write-Info "Would append: AuthorizedPrincipalsFile $PrincipalsDir\\%u"
    }} else {{
        Add-Content -Path $SshdConfig -Value "AuthorizedPrincipalsFile $PrincipalsDir\\%u"
        Write-Ok "Added AuthorizedPrincipalsFile directive"
    }}
}}

# --- Step 6: Validate sshd config ---
Write-Info "Validating sshd configuration (sshd -T)..."
$sshdExe = (Get-Command sshd.exe -ErrorAction SilentlyContinue).Source
if (-not $sshdExe) {{ $sshdExe = Join-Path $env:ProgramFiles 'OpenSSH\\sshd.exe' }}
if ($DryRun) {{
    Write-Info "Would run: sshd -T"
}} elseif (Test-Path $sshdExe) {{
    & $sshdExe -T 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {{
        Write-Ok "sshd configuration is valid"
    }} else {{
        Write-Err "sshd configuration test failed. Restoring backup..."
        Copy-Item -Path $backup -Destination $SshdConfig -Force
        Write-Err "Backup restored. Inspect sshd_config manually."
        exit 1
    }}
}} else {{
    Write-Warn2 "sshd.exe not found - skipping config validation"
}}

# --- Step 7: Restart sshd ---
Write-Info "Restarting sshd service..."
if ($DryRun) {{
    Write-Info "Would run: Restart-Service sshd"
}} else {{
    try {{
        Restart-Service -Name sshd -Force
        Write-Ok "sshd restarted successfully"
    }} catch {{
        Write-Warn2 "Restart-Service failed: $_  - check service status manually."
    }}
}}

Write-Host ""
Write-Host "========================================" -ForegroundColor White
if ($DryRun) {{
    Write-Host "Dry run complete - no changes were made." -ForegroundColor Yellow
}} else {{
    Write-Host "Setup complete!" -ForegroundColor Green
}}
Write-Host "========================================" -ForegroundColor White
Write-Host ""

if (-not $DryRun) {{
    Write-Info "Next steps:"
    Write-Info "  1. For each Windows user, create a principals file:"
    Write-Info "     Set-Content -Path '$PrincipalsDir\\<username>' -Value 'principal_name'"
    Write-Info "  2. Sign user keys with the CA in UCM (SSH > Certificates > Sign)"
    Write-Info "  3. Users can now log in with their signed certificate"
}}

}} catch {{
    $ScriptFailed = $true
    Write-Host ""
    Write-Err "Setup FAILED: $_"
    if ($_.ScriptStackTrace) {{
        Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
    }}
    Write-Host ""
    Write-Info "Full log saved to: $LogFile"
}} finally {{
    try {{ Stop-Transcript | Out-Null }} catch {{ }}
    Write-Host ""
    if ($ScriptFailed) {{
        Pause-IfInteractive 'An error occurred. Press Enter to close this window...'
        exit 1
    }} else {{
        Pause-IfInteractive
    }}
}}
'''


def _host_ca_script_windows(pub_key, ca_label, hostname):
    ps_pub_key = pub_key.replace("'", "''")
    ps_label = ca_label.replace("'", "''")
    hostname_init = hostname if hostname else ''
    return rf'''<#
.SYNOPSIS
    SSH Host CA Trust Setup Script (Windows OpenSSH Server)
    CA: {ca_label}
    Generated by UCM (Ultimate Certificate Manager)

.DESCRIPTION
    Configures the Windows OpenSSH Server to present a host certificate signed
    by the above CA. The host key signing itself must be performed via UCM
    (the CA private key is not exposed); this script prepares everything else
    and adds the HostCertificate directive once the cert is in place.

.PARAMETER DryRun
    Preview without modifying anything.

.PARAMETER NonInteractive
    Skip all prompts (OpenSSH install, end pause). Use in CI/automation.

.PARAMETER NoPause
    Do not pause at the end (default is to pause so the window stays open).

.EXAMPLE
    powershell -ExecutionPolicy Bypass -File .\\ssh_ca_setup.ps1
#>

[CmdletBinding()]
param(
    [switch]$DryRun,
    [switch]$NonInteractive,
    [switch]$NoPause
)

$ErrorActionPreference = 'Stop'

function Write-Info  ($msg) {{ Write-Host "[INFO]  $msg" -ForegroundColor Cyan }}
function Write-Ok    ($msg) {{ Write-Host "[OK]    $msg" -ForegroundColor Green }}
function Write-Warn2 ($msg) {{ Write-Host "[WARN]  $msg" -ForegroundColor Yellow }}
function Write-Err   ($msg) {{ Write-Host "[ERROR] $msg" -ForegroundColor Red }}

function Pause-IfInteractive {{
    param([string]$Message = 'Press Enter to close this window...')
    if ($NoPause -or $NonInteractive) {{ return }}
    try {{ Read-Host -Prompt $Message | Out-Null }} catch {{ Start-Sleep -Seconds 30 }}
}}

# --- Transcript log (always-on so output survives even if window closes) ---
$LogFile = Join-Path $env:TEMP ("ucm_ssh_host_ca_setup_" + (Get-Date -Format 'yyyyMMdd_HHmmss') + ".log")
try {{ Start-Transcript -Path $LogFile -Force | Out-Null }} catch {{ }}
Write-Host "Log file: $LogFile" -ForegroundColor DarkGray

$ScriptFailed = $false
try {{

# --- Configuration ---
$SshDir     = Join-Path $env:ProgramData 'ssh'
$CaKeyDir   = Join-Path $SshDir 'ssh_ca_keys'
$CaKeyFile  = Join-Path $CaKeyDir 'host_ca.pub'
$SshdConfig = Join-Path $SshDir 'sshd_config'
$Hostname   = '{hostname_init}'

# --- Admin check ---
$identity  = [Security.Principal.WindowsIdentity]::GetCurrent()
$principal = New-Object Security.Principal.WindowsPrincipal($identity)
if (-not $principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)) {{
    Write-Err "This script must be run as Administrator."
    Write-Info "Right-click PowerShell -> Run as Administrator, then re-run this script."
    throw "Not running as Administrator"
}}

if (-not $Hostname) {{
    try {{ $Hostname = [System.Net.Dns]::GetHostByName($env:COMPUTERNAME).HostName }} catch {{ $Hostname = $env:COMPUTERNAME }}
}}

Write-Host "========================================" -ForegroundColor White
Write-Host "SSH Host CA Trust Setup (Windows)"      -ForegroundColor White
Write-Host "CA:   {ca_label}"
Write-Host "Host: $Hostname"
if ($DryRun) {{
    Write-Host ">>> DRY RUN - no changes will be made <<<" -ForegroundColor Yellow
}}
Write-Host "========================================" -ForegroundColor White
Write-Host ""

$sshdSvc = Get-Service -Name sshd -ErrorAction SilentlyContinue
$fodInstalled = $false
$wingetInstalled = $false
try {{
    $cap = Get-WindowsCapability -Online -Name 'OpenSSH.Server~~~~0.0.1.0' -ErrorAction SilentlyContinue
    if ($cap -and $cap.State -eq 'Installed') {{ $fodInstalled = $true }}
}} catch {{ }}
$wingetSshdPath = Join-Path $env:ProgramFiles 'OpenSSH\sshd.exe'
if (Test-Path $wingetSshdPath) {{ $wingetInstalled = $true }}

if ($fodInstalled) {{
    Write-Info "Detected OpenSSH Server install: Windows Features-on-Demand"
    Write-Info "  Binary: $env:WINDIR\System32\OpenSSH\sshd.exe"
}}
if ($wingetInstalled) {{
    Write-Info "Detected OpenSSH Server install: winget / standalone"
    Write-Info "  Binary: $wingetSshdPath"
}}
Write-Info "CA public key will be installed to: $CaKeyFile"
Write-Info "sshd_config will be updated at:    $SshdConfig"

if (-not ($fodInstalled -or $wingetInstalled -or $sshdSvc)) {{
    Write-Warn2 "OpenSSH Server is not installed (neither FoD nor winget detected)."
    $doInstall = $false
    if ($DryRun) {{
        Write-Info "Would offer to install OpenSSH.Server via Features-on-Demand (skipped in -DryRun)."
    }} elseif ($NonInteractive) {{
        Write-Err "OpenSSH Server is missing and -NonInteractive was supplied."
        Write-Info "Install manually with one of:"
        Write-Info "  Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0"
        Write-Info "  winget install Microsoft.OpenSSH.Beta"
        throw "OpenSSH Server missing"
    }} else {{
        $resp = Read-Host "Install OpenSSH Server via Features-on-Demand now? [Y/n]"
        if ($resp -eq '' -or $resp -match '^[Yy]') {{ $doInstall = $true }}
    }}
    if ($doInstall) {{
        Write-Info "Installing OpenSSH.Server via Add-WindowsCapability (this may take 1-2 minutes)..."
        try {{
            Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 -ErrorAction Stop | Out-Null
        }} catch {{
            $errMsg = $_.Exception.Message
            Write-Err "Add-WindowsCapability failed: $errMsg"
            Write-Host ""
            Write-Host "---- Diagnostic ----" -ForegroundColor Yellow
            if ($errMsg -match '0x8024500c|WU_E_PT_WMT_MISSING') {{
                Write-Host "Cause: 0x8024500c (WU_E_PT_WMT_MISSING)" -ForegroundColor Yellow
                Write-Host "  This machine is configured to use WSUS (group policy), but the WSUS server"
                Write-Host "  does not host the OpenSSH Features-on-Demand source, so Windows refuses to"
                Write-Host "  download it from Microsoft Update."
            }} elseif ($errMsg -match '0x800f0954') {{
                Write-Host "Cause: 0x800f0954 (CBS_E_INVALID_WINDOWS_UPDATE_COUNT_WSUS)" -ForegroundColor Yellow
                Write-Host "  Group policy forbids reaching Microsoft Update for Features-on-Demand."
            }} elseif ($errMsg -match '0x80240438|0x8024402c|0x80072ee2|0x80072efd') {{
                Write-Host "Cause: Windows Update / WSUS connectivity error ($errMsg)" -ForegroundColor Yellow
                Write-Host "  The Windows Update client cannot reach its configured update source."
            }} else {{
                Write-Host "Cause: see error message above." -ForegroundColor Yellow
            }}
            $regAU = 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU'
            $useWUServer = (Get-ItemProperty -Path $regAU -Name UseWUServer -ErrorAction SilentlyContinue).UseWUServer
            $wuServer = (Get-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate' -Name WUServer -ErrorAction SilentlyContinue).WUServer
            if ($useWUServer -eq 1) {{
                Write-Host ("  Detected WSUS policy: UseWUServer=1, WUServer={0}" -f $wuServer)
            }} else {{
                Write-Host "  No WSUS policy detected (UseWUServer != 1)."
            }}
            Write-Host ""
            Write-Host "Resolution options (ask your Windows / AD team — do NOT bypass policy yourself):" -ForegroundColor Cyan
            Write-Host "  1. Ask the WSUS admin to approve the OpenSSH FoD package, OR enable the policy"
            Write-Host "     'Specify settings for optional component installation and component repair'"
            Write-Host "     with 'Download repair content ... directly from Windows Update' enabled"
            Write-Host "     (Computer Config > Admin Templates > System)."
            Write-Host "  2. Install offline from a Features-on-Demand ISO matching this Windows build:"
            Write-Host "     Add-WindowsCapability -Online -Name OpenSSH.Server~~~~0.0.1.0 -Source <FoD-ISO>\LanguagesAndOptionalFeatures"
            Write-Host "  3. Install OpenSSH Server manually via Settings > Apps > Optional features."
            Write-Host "Re-run this script once OpenSSH Server is installed and running."
            Write-Host "--------------------" -ForegroundColor Yellow
            throw
        }}
        Set-Service -Name sshd -StartupType 'Automatic'
        Start-Service sshd
        if (-not (Get-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -ErrorAction SilentlyContinue)) {{
            try {{
                New-NetFirewallRule -Name 'OpenSSH-Server-In-TCP' -DisplayName 'OpenSSH Server (sshd)' `
                    -Enabled True -Direction Inbound -Protocol TCP -Action Allow -LocalPort 22 | Out-Null
                Write-Ok "Firewall rule added (TCP/22 inbound)"
            }} catch {{
                Write-Warn2 "Could not create firewall rule: $_"
            }}
        }}
        $sshdSvc = Get-Service -Name sshd
        Write-Ok "OpenSSH Server installed and started"
    }} elseif (-not $DryRun) {{
        throw "OpenSSH Server is required. Install it and re-run this script."
    }}
}} elseif ($sshdSvc) {{
    Write-Info "sshd service detected (status: $($sshdSvc.Status))"
}} else {{
    Write-Warn2 "OpenSSH binaries detected but sshd service is not registered."
    Write-Info "Run: Set-Service -Name sshd -StartupType 'Automatic'; Start-Service sshd"
}}

# --- Step 1: Create CA key directory ---
if (-not $DryRun) {{
    New-Item -ItemType Directory -Path $CaKeyDir -Force | Out-Null
    Write-Ok "CA key directory ready: $CaKeyDir"
}}

# --- Step 2: Write CA public key ---
$CaPubKey = @'
{ps_pub_key}
'@

if (-not $DryRun) {{
    Set-Content -Path $CaKeyFile -Value $CaPubKey -Encoding ASCII -NoNewline:$false
    Write-Ok "CA public key written: $CaKeyFile"
}} else {{
    Write-Info "Would write CA public key to: $CaKeyFile"
}}

# --- Step 3: Backup sshd_config ---
if (-not (Test-Path $SshdConfig)) {{ Write-Err "sshd_config not found at $SshdConfig"; exit 1 }}
$backup = "$SshdConfig.bak.$(Get-Date -Format 'yyyyMMddHHmmss')"
if (-not $DryRun) {{ Copy-Item $SshdConfig $backup; Write-Ok "Backup: $backup" }} else {{ Write-Info "Would back up to: $backup" }}

# --- Step 4: Locate a host key ---
$hostKey = $null
foreach ($kt in @('ed25519','ecdsa','rsa')) {{
    $candidate = Join-Path $SshDir "ssh_host_${{kt}}_key.pub"
    if (Test-Path $candidate) {{
        $hostKey = Join-Path $SshDir "ssh_host_${{kt}}_key"
        break
    }}
}}
if (-not $hostKey) {{
    Write-Err "No SSH host key found in $SshDir."
    Write-Info "Generate with: ssh-keygen -A"
    exit 1
}}
$certFile = "$hostKey-cert.pub"
Write-Info "Found host key: $hostKey"

if (Test-Path $certFile) {{
    Write-Warn2 "Host certificate already exists: $certFile"
    Write-Warn2 "If you want to re-sign, remove it first and re-run this script."
}} else {{
    Write-Host ""
    Write-Warn2 "Host key signing requires the CA private key, which is managed by UCM."
    Write-Info "Sign via UCM:"
    Write-Info "  1. Copy the host public key to a workstation: $hostKey.pub"
    Write-Info "  2. UCM > SSH > Certificates > Sign Host Key"
    Write-Info "  3. Principals: $Hostname"
    Write-Info "  4. Place the resulting cert at: $certFile"
    Write-Host ""
}}

# --- Step 5: Add HostCertificate directive ---
$existingConfig = Get-Content $SshdConfig -Raw
if ($existingConfig -match '(?m)^\\s*HostCertificate\\b') {{
    Write-Warn2 "HostCertificate is already configured. Skipping."
}} else {{
    if ($DryRun) {{
        Write-Info "Would append: HostCertificate $certFile"
    }} else {{
        Add-Content -Path $SshdConfig -Value ""
        Add-Content -Path $SshdConfig -Value "# SSH Host Certificate - added by UCM setup script"
        Add-Content -Path $SshdConfig -Value "HostCertificate $certFile"
        Write-Ok "Added HostCertificate directive"
    }}
}}

# --- Step 6: Validate ---
$sshdExe = (Get-Command sshd.exe -ErrorAction SilentlyContinue).Source
if (-not $sshdExe) {{ $sshdExe = Join-Path $env:ProgramFiles 'OpenSSH\\sshd.exe' }}
if (-not $DryRun -and (Test-Path $sshdExe)) {{
    & $sshdExe -T 2>&1 | Out-Null
    if ($LASTEXITCODE -eq 0) {{
        Write-Ok "sshd configuration is valid"
    }} else {{
        Write-Err "sshd configuration test failed. Restoring backup..."
        Copy-Item $backup $SshdConfig -Force
        exit 1
    }}
}}

# --- Step 7: Restart sshd if cert is in place ---
if (-not $DryRun) {{
    if (Test-Path $certFile) {{
        try {{ Restart-Service -Name sshd -Force; Write-Ok "sshd restarted" }} catch {{ Write-Warn2 "sshd restart failed: $_" }}
    }} else {{
        Write-Warn2 "Skipping sshd restart - host certificate not present yet."
        Write-Warn2 "Sign the host key in UCM, place the cert, then: Restart-Service sshd"
    }}
}}

Write-Host ""
Write-Host "========================================" -ForegroundColor White
if ($DryRun) {{
    Write-Host "Dry run complete - no changes were made." -ForegroundColor Yellow
}} else {{
    Write-Host "Setup complete!" -ForegroundColor Green
}}
Write-Host "========================================" -ForegroundColor White
Write-Host ""

Write-Info "Clients should add to their known_hosts:"
Write-Info "  @cert-authority * <CA public key from $CaKeyFile>"

}} catch {{
    $ScriptFailed = $true
    Write-Host ""
    Write-Err "Setup FAILED: $_"
    if ($_.ScriptStackTrace) {{
        Write-Host $_.ScriptStackTrace -ForegroundColor DarkGray
    }}
    Write-Host ""
    Write-Info "Full log saved to: $LogFile"
}} finally {{
    try {{ Stop-Transcript | Out-Null }} catch {{ }}
    Write-Host ""
    if ($ScriptFailed) {{
        Pause-IfInteractive 'An error occurred. Press Enter to close this window...'
        exit 1
    }} else {{
        Pause-IfInteractive
    }}
}}
'''


@bp.route('/api/v2/ssh/cas/<int:ca_id>/krl', methods=['GET'])
@require_auth(['read:ssh'])
def get_ssh_ca_krl(ca_id):
    """Download the KRL (Key Revocation List) for this CA."""
    try:
        krl_data = SSHKRLService.generate_krl(ca_id)
        ca = SSHCertificateAuthority.query.get(ca_id)
        ca_name = ca.descr if ca else 'unknown'

        return Response(
            krl_data,
            mimetype='application/octet-stream',
            headers={
                'Content-Disposition': f'attachment; filename="ssh_ca_{re.sub(r"[^a-zA-Z0-9_.-]", "_", ca_name)}_krl"'
            }
        )
    except ValueError as e:
        return error_response(str(e), 404)
    except RuntimeError as e:
        logger.error(f"Failed to generate KRL for CA {ca_id}: {e}")
        return error_response('Failed to generate KRL', 500)
    except Exception as e:
        logger.error(f"Failed to generate KRL: {e}")
        return error_response('Failed to generate KRL', 500)
