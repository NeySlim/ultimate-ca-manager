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
from email.utils import format_datetime
from datetime import timezone

from flask import Blueprint, request, Response

from api.v2.ssh.validation import validate_setup_hostname
from models.ssh import SSHCertificateAuthority
from utils.sanitize import content_disposition
from services.ssh_ca_service import SSHCAService
from services.ssh_krl_service import SSHKRLService

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

        safe_name = ca.descr.replace(' ', '_').replace('"', '').replace("'", '')

        if platform == 'windows':
            mimetype = 'text/x-powershell'
            ext = '.ps1'
        else:
            mimetype = 'text/x-shellscript'
            ext = '.sh'

        return Response(
            script,
            mimetype=mimetype,
            headers={
                'Content-Disposition': content_disposition(safe_name, ext, fallback=ca.refid, prefix='ssh_ca_setup_'),
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
                'Content-Disposition': content_disposition(ca.descr.replace(' ', '_'), '_ca.pub', fallback=ca.refid, disposition='inline'),
                'Cache-Control': 'no-cache, no-store, must-revalidate',
            }
        )
    except Exception as e:
        logger.error(f"Failed to serve public key for refid {refid}: {e}")
        return Response('Error retrieving public key', status=500, mimetype='text/plain')


@bp.route('/ssh/setup/<refid>/agent', methods=['GET'])
def get_agent_installer(refid):
    """The installer of the SSH agent for this CA (issue #451): POSIX sh, no secret in it."""
    from api.v2.ssh.agent_script import installer_script, shell_safe_base_url

    def refusal(message, status):
        return Response(f'#!/bin/sh\necho "Error: {message}" >&2\nexit 1\n', status=status,
                        mimetype='text/x-shellscript')
    ca = SSHCertificateAuthority.query.filter_by(refid=refid).first()
    if not ca:
        return refusal('SSH CA not found', 404)
    base_url = shell_safe_base_url(request.url_root)
    if not base_url:
        return refusal('this server is reached under a name the agent cannot use', 400)
    return Response(installer_script(base_url, ca), mimetype='text/x-shellscript', headers={
        'Content-Disposition': content_disposition(ca.descr.replace(' ', '_'), '.sh', fallback=ca.refid,
                                                   prefix='ucm_ssh_agent_'),
        'Cache-Control': 'no-cache, no-store, must-revalidate',
    })


def _etag_matches(header, etag):
    """RFC 9110 13.1.2: If-None-Match compares weakly, and ``*`` matches any current KRL."""
    if not header:
        return False
    for candidate in header.split(','):
        candidate = candidate.strip()
        if candidate == '*' or candidate.removeprefix('W/') == etag:
            return True
    return False


@bp.route('/ssh/krl/<refid>', methods=['GET'])
def get_public_krl(refid):
    """The published KRL of an SSH CA, public as a CRL is: ETag and X-KRL-Version carry the
    KRL version, which changes only with the revocations; a matching If-None-Match gets 304."""
    ca = SSHCertificateAuthority.query.filter_by(refid=refid).first()
    if not ca:
        return Response('SSH CA not found\n', status=404, mimetype='text/plain')
    try:
        krl = SSHKRLService.published(ca.id)
    except Exception as e:
        logger.error(f"Failed to publish the KRL of SSH CA {ca.id}: {e}")
        return Response('KRL unavailable\n', status=503, mimetype='text/plain',
                        headers={'Retry-After': '60'})
    if request.args.get('host'):
        from services.ssh_host_service import krl_pulled
        krl_pulled(request.args['host'])
    etag = f'"{krl["version"]}"'
    headers = {
        'ETag': etag,
        'X-KRL-Version': str(krl['version']),
        # Stored by caches, revalidated on every use: a revocation is seen at the next pull
        'Cache-Control': 'public, no-cache',
        'Last-Modified': format_datetime(krl['updated_at'].replace(tzinfo=timezone.utc), usegmt=True),
    }
    if _etag_matches(request.headers.get('If-None-Match'), etag):
        return Response(status=304, headers=headers)
    headers['Content-Disposition'] = content_disposition(
        ca.descr.replace(' ', '_'), '.krl', fallback=ca.refid, prefix='ssh_ca_')
    return Response(krl['data'], mimetype='application/octet-stream', headers=headers)
