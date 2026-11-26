"""Public routes of the SSH host agent (issue #451): enrollment with a single-use token.

No session and no API key: a host authenticates with its enrollment token. Answers are JSON,
or ``key=value`` lines when the client asks for text/plain (the sh agent reads no JSON).
"""
import logging

from flask import Blueprint, Response, jsonify, request

from services.audit_service import AuditService
from services import ssh_host_service as hosts
from utils.datetime_utils import utc_isoformat
from utils.trusted_proxy import client_ip

logger = logging.getLogger(__name__)

bp = Blueprint('ssh_host_agent', __name__)

MAX_BODY = 64 * 1024


def _wants_text():
    return 'text/plain' in (request.headers.get('Accept') or '')


def _answer(fields, status=200):
    if _wants_text():
        # One value per line: none of them holds a line break
        body = ''.join(f'{k}={"" if v is None else v}\n' for k, v in fields.items())
        return Response(body, status=status, mimetype='text/plain', headers={'Cache-Control': 'no-store'})
    response = jsonify(fields)
    response.status_code = status
    response.headers['Cache-Control'] = 'no-store'
    return response


def _body():
    if request.content_length is not None and request.content_length > MAX_BODY:
        raise hosts.EnrollmentRefused(413, 'request too large')
    data = request.get_json(silent=True)
    if not isinstance(data, dict):
        raise hosts.EnrollmentRefused(400, 'a JSON object is required')
    return data


@bp.route('/ssh/enroll/<refid>', methods=['POST'])
def enroll_host(refid):
    """Body: ``token``, ``public_key`` (the host key, ``type base64``), optional ``principals``
    (a subset of the token's; all of them by default). 201 with the host refid and certificate."""
    ip = client_ip()
    try:
        data = _body()
        host, cert = hosts.enroll(refid, data.get('token'), data.get('public_key'),
                                  data.get('principals'), ip=ip)
    except hosts.EnrollmentRefused as e:
        AuditService.log_action(action='ssh_host_enrollment_refused', resource_type='ssh_host',
                                resource_name=refid[:64], details=f'SSH host enrollment refused: {e.reason}',
                                success=False, username='ssh-host-agent')
        return _answer({'error': e.public}, e.status)
    AuditService.log_action(
        action='ssh_host_enrolled', resource_type='ssh_host', resource_id=str(host.id), resource_name=host.name,
        details=(f"SSH host enrolled under CA '{host.ca.descr}' for {', '.join(host.get_principals())}: "
                 f"key {host.fingerprint}, certificate #{cert.serial}"),
        success=True, username='ssh-host-agent')
    return _answer({'host_refid': host.refid, 'certificate': cert.certificate,
                    'principals': ','.join(host.get_principals()),
                    'valid_to': utc_isoformat(cert.valid_to), 'renew_percent': host.renew_percent}, 201)
