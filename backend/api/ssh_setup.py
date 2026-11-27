"""
Public SSH CA Setup Script Endpoint

Serves setup scripts via a public URL using CA refid (UUID).
No authentication required — designed for `curl | sudo bash` usage.

Security:
- Uses refid (UUID) not sequential id — unguessable
- Read-only — only serves public key + shell script
- No sensitive data exposed (private key is never included)
- Rate limiting via CA-level access (same as CDP/OCSP)
"""

import logging
import re
from flask import Blueprint, request, Response

from api.v2.ssh.script_quoting import one_line
from api.v2.ssh.validation import validate_setup_hostname
from models.ssh import SSHCertificateAuthority
from services.ssh_ca_service import SSHCAService


def _file_name(descr):
    # The same file name as the authenticated routes: ASCII letters, digits, '_', '.' and '-'
    return re.sub(r'[^a-zA-Z0-9_.-]', '_', one_line(descr))


logger = logging.getLogger(__name__)

bp = Blueprint('ssh_setup_public', __name__)


@bp.route('/ssh/setup/<refid>', methods=['GET'])
def get_public_setup_script(refid):
    """Serve SSH CA setup script publicly (like CDP serves CRLs).

    Usage (Linux/macOS):
        curl -sSL https://ucm.example.com:8443/ssh/setup/<refid> | sudo bash
        curl -sSL https://ucm.example.com:8443/ssh/setup/<refid>?type=host | sudo bash

    Usage (Windows, elevated PowerShell):
        iwr -useb https://ucm.example.com:8443/ssh/setup/<refid>?platform=windows | iex
    """
    try:
        ca = SSHCertificateAuthority.query.filter_by(refid=refid).first()
        if not ca:
            return Response('#!/bin/sh\necho "Error: SSH CA not found"\nexit 1\n',
                            status=404, mimetype='text/x-shellscript')

        pub_key = SSHCAService.get_public_key(ca.id)

        ca_type = request.args.get('type', '').strip().lower()
        if ca_type and ca_type not in ('user', 'host'):
            return Response('#!/bin/sh\necho "Error: Invalid type. Use ?type=user or ?type=host"\nexit 1\n',
                            status=400, mimetype='text/x-shellscript')
        if not ca_type:
            ca_type = ca.ca_type

        hostname = request.args.get('hostname', '').strip()
        hostname_err = validate_setup_hostname(hostname)
        if hostname_err:
            return Response(
                '#!/bin/sh\necho "Error: Invalid hostname format"\nexit 1\n',
                status=400,
                mimetype='text/x-shellscript',
            )

        platform = request.args.get('platform', 'unix').strip().lower()
        if platform not in ('unix', 'linux', 'macos', 'windows'):
            return Response('#!/bin/sh\necho "Error: Invalid platform. Use ?platform=unix or ?platform=windows"\nexit 1\n',
                            status=400, mimetype='text/x-shellscript')

        # Reuse the script generators from the authenticated endpoint
        from api.v2.ssh.setup_scripts import _generate_setup_script
        script = _generate_setup_script(ca, pub_key, ca_type, hostname, platform)

        # A header carries only latin-1, and a stored description may hold a line break
        safe_name = _file_name(ca.descr)

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
                'Content-Disposition': f'attachment; filename="{filename}"',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
            }
        )
    except ValueError as e:
        logger.warning(f"SSH setup script error for refid {refid}: {e}")
        return Response(f'#!/bin/sh\necho "Error: {e}"\nexit 1\n',
                        status=404, mimetype='text/x-shellscript')
    except Exception as e:
        logger.error(f"Failed to generate public SSH setup script: {e}")
        return Response('#!/bin/sh\necho "Error: Failed to generate setup script"\nexit 1\n',
                        status=500, mimetype='text/x-shellscript')


@bp.route('/ssh/setup/<refid>/public-key', methods=['GET'])
def get_public_key(refid):
    """Serve SSH CA public key publicly (for manual setup)."""
    try:
        ca = SSHCertificateAuthority.query.filter_by(refid=refid).first()
        if not ca:
            return Response('SSH CA not found', status=404, mimetype='text/plain')

        pub_key = SSHCAService.get_public_key(ca.id)

        return Response(
            pub_key + '\n',
            mimetype='text/plain',
            headers={
                'Content-Disposition': f'inline; filename="{_file_name(ca.descr)}_ca.pub"',
                'Cache-Control': 'no-cache, no-store, must-revalidate',
            }
        )
    except Exception as e:
        logger.error(f"Failed to serve public key for refid {refid}: {e}")
        return Response('Error retrieving public key', status=500, mimetype='text/plain')
