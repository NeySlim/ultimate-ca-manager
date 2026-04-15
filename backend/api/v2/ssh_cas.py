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

        script = _generate_setup_script(ca, pub_key, ca_type, hostname)
        safe_name = re.sub(r'[^a-zA-Z0-9_.-]', '_', ca.descr)

        return Response(
            script,
            mimetype='text/x-shellscript',
            headers={
                'Content-Disposition': f'attachment; filename="ssh_ca_setup_{safe_name}.sh"'
            }
        )
    except ValueError as e:
        return error_response(str(e), 404)
    except Exception as e:
        logger.error(f"Failed to generate SSH CA setup script: {e}")
        return error_response('Failed to generate setup script', 500)


def _generate_setup_script(ca, pub_key, ca_type, hostname):
    """Build a POSIX-compliant shell script for SSH CA trust configuration."""
    safe_key = pub_key.strip().replace("'", "'\\''")
    ca_label = ca.descr.replace("'", "'\\''")

    if ca_type == 'user':
        return _user_ca_script(safe_key, ca_label)
    return _host_ca_script(safe_key, ca_label, hostname)


def _user_ca_script(pub_key, ca_label):
    return f'''#!/bin/sh
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
    return f'''#!/bin/sh
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
        return error_response(str(e), 500)
    except Exception as e:
        logger.error(f"Failed to generate KRL: {e}")
        return error_response('Failed to generate KRL', 500)
