"""
SSH CA public-key and setup-script endpoints.
"""

import re

from flask import request, Response

from auth.unified import require_auth
from utils.response import error_response
from services.ssh_ca_service import SSHCAService
from models.ssh import SSHCertificateAuthority

from .helpers import bp, logger
from .setup_scripts import _generate_setup_script


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
