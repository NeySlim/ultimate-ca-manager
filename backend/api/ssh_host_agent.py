"""Public routes of the SSH host agent (issue #451): enrollment with a single-use token, and
renewal by a signature of a server challenge with the certified host key.

No session and no API key: a host authenticates with its enrollment token, then with its key;
UCM keeps no secret of the host. Answers are JSON,
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
    """Body: ``token``, ``public_key`` (the host key, ``type base64``), ``signature`` (the token
    signed with that key, ``ssh-keygen -Y sign -n ucm-ssh-host-enrollment``), optional ``principals``
    (a subset of the token's; all of them by default). 201 with the host refid and certificate."""
    ip = client_ip()
    try:
        data = _body()
        host, cert = hosts.enroll(refid, data.get('token'), data.get('public_key'),
                                  data.get('principals'), ip=ip, signature=data.get('signature'))
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


@bp.route('/ssh/renew/<host_refid>/challenge', methods=['POST'])
def renewal_challenge(host_refid):
    """``due=0`` with ``renew_after`` while the certificate is young; ``due=1`` with a
    ``challenge`` to sign (``ssh-keygen -Y sign -n <namespace>``) once it is in its last share."""
    try:
        answer = hosts.challenge(host_refid)
    except hosts.RenewalRefused as e:
        if e.audited:
            AuditService.log_action(action='ssh_host_renewal_refused', resource_type='ssh_host',
                                    resource_name=host_refid[:64], details=f'SSH host renewal refused: {e.reason}',
                                    success=False, username='ssh-host-agent')
        return _answer({'error': e.public, 'state': e.state}, e.status)
    if 'renew_after' in answer:
        answer['renew_after'] = utc_isoformat(answer['renew_after'])
    return _answer(answer)


@bp.route('/ssh/renew/<host_refid>', methods=['POST'])
def renew_host(host_refid):
    """Body: ``challenge`` and ``signature`` (the armored SSH signature). 200 with the new certificate."""
    try:
        data = _body()
        host, cert = hosts.renew(host_refid, data.get('challenge'), data.get('signature'))
    except hosts.EnrollmentRefused as e:
        AuditService.log_action(action='ssh_host_renewal_refused', resource_type='ssh_host',
                                resource_name=host_refid[:64], details=f'SSH host renewal refused: {e.reason}',
                                success=False, username='ssh-host-agent')
        return _answer({'error': e.public, 'state': getattr(e, 'state', 'refused')}, e.status)
    AuditService.log_action(
        action='ssh_host_renewed', resource_type='ssh_host', resource_id=str(host.id), resource_name=host.name,
        details=f"SSH host certificate renewed for {', '.join(host.get_principals())}: certificate #{cert.serial}",
        success=True, username='ssh-host-agent')
    return _answer({'certificate': cert.certificate, 'valid_to': utc_isoformat(cert.valid_to)})
