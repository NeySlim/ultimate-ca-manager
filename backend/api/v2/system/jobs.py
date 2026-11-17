"""Background jobs: read, list, cancel; and the answer of a route that starts one.

A starting route waits at most JOB_WAIT_SECONDS: a job finished by then answers exactly what
the route answered before jobs existed; otherwise 202 with a Location to follow (RFC 9110
§15.3.3). ``Prefer: respond-async`` answers 202 at once, ``wait=N`` shortens the wait
(RFC 7240 §4.1, §4.3).
"""
import logging

from flask import g, request

from api.v2.system import bp
from models import db
from auth.unified import has_permission, require_auth
from services import jobs
from utils.response import error_response, success_response

logger = logging.getLogger(__name__)

LIST_LIMIT_MAX = 100
_FINAL_MESSAGES = {
    jobs.EXECUTOR_LOST: 'The job stopped before the end: the process running it was lost',
    jobs.NOT_TAKEN: 'The job was never started',
    'cancelled': 'The job was cancelled',
    'error': 'The job failed',
}


def location(job_id):
    return f'/api/v2/system/jobs/{job_id}'


def parse_prefer(values):
    """{preference: value or True} from Prefer header fields (RFC 7240 §2), names lowercased."""
    found = {}
    for value in values:
        for item in value.split(','):
            head = item.split(';', 1)[0].strip()
            if not head:
                continue
            name, _, token = head.partition('=')
            name = name.strip().lower()
            if name and name not in found:
                found[name] = token.strip().strip('"') if _ else True
    return found


def _with_headers(response, **headers):
    body, status = response
    for name, value in headers.items():
        body.headers[name.replace('_', '-')] = value
    body.headers.add('Vary', 'Prefer')
    return body, status


def accepted(row, applied=None, extra=None):
    response = success_response(
        data={'job': jobs.public_view(row, with_result=False), **(extra or {})},
        message='Accepted: the job runs in the background', status=202)
    headers = {'Location': location(row['id'])}
    if applied:
        headers['Preference_Applied'] = applied
    return _with_headers(response, **headers)


def final_response(row, extra=None):
    """The answer of a finished job: the route's own response, or why there is none.
    ``extra`` joins the data of a success only (a generated password, never stored)."""
    import json
    result = json.loads(row['result']) if row['result'] else None
    if result is not None:
        if result['code'] < 400:
            data = result['data']
            if extra and isinstance(data, dict):
                data = {**data, **extra}
            return _with_headers(success_response(
                data=data, message=result['message'], status=result['code']))
        return _with_headers(error_response(result['message'], result['code'],
                                            problem_type=result.get('problem_type')))
    jt = jobs.job_type(row['kind'])
    reason = row['reason'] or 'error'
    message = (jt.messages.get(reason) if jt else None) or _FINAL_MESSAGES.get(reason, 'The job failed')
    code = 409 if row['state'] == jobs.CANCELLED else 500
    return _with_headers(error_response(message, code, details={'job': jobs.public_view(row, False)}))


def busy_response(exc):
    """409 naming the active job that holds the slot."""
    row = exc.job
    if row is None:
        return _with_headers(error_response('Another job is active: try again once it ends', 409))
    job = {k: v for k, v in jobs.public_view(row, False).items()
           if k in ('id', 'kind', 'state', 'created_at', 'requested_by')}
    return _with_headers(error_response(
        f"Another job is active ({row['kind']}): try again once it ends", 409,
        details={'job': job}, meta={'location': location(row['id'])}))


def suspended_response():
    """503 with Retry-After: no job starts during a cluster maintenance."""
    from services.cluster_maintenance import refusal
    response = refusal(message=jobs.JobsSuspended.MESSAGE)
    response.headers.add('Vary', 'Prefer')
    return response, 503


def started_response(job_id, extra=None):
    """What a starting route answers for ``job_id``: bounded wait, then 200 or 202.
    ``extra`` is data the route holds in memory only, given once in this answer."""
    prefs = parse_prefer(request.headers.getlist('Prefer'))
    asynchronous = bool(prefs.get('respond-async'))
    wait = prefs.get('wait')
    # ASCII digits only: str.isdigit() also takes '²', which int() refuses after the job exists
    if isinstance(wait, str) and wait.isascii() and wait.isdigit():
        seconds = min(int(wait), jobs.JOB_WAIT_SECONDS)
    else:
        # respond-async alone: 202 at once; with wait=N, after at most N seconds (RFC 7240 §4.1)
        seconds = 0 if asynchronous else jobs.JOB_WAIT_SECONDS
    if asynchronous and seconds == 0:
        return accepted(jobs.get_job(job_id), applied='respond-async', extra=extra)
    row = jobs.wait_for_job(job_id, seconds)
    if row is not None and row['state'] in jobs.FINAL_STATES:
        return final_response(row, extra)
    return accepted(row, applied='respond-async' if asynchronous else None, extra=extra)


def _readable(kind):
    jt = jobs.job_type(kind)
    return jt is not None and has_permission(jt.permission, g.permissions or [])


@bp.route('/api/v2/system/jobs', methods=['GET'])
@require_auth()
def list_jobs():
    """The latest jobs of the kinds the caller may read. ?kind=, ?state=active|final, ?limit="""
    kinds = [k for k in jobs.types() if _readable(k)]
    asked = request.args.get('kind')
    if asked:
        kinds = [k for k in kinds if k == asked]
    state = request.args.get('state')
    if state not in (None, '', 'active', 'final'):
        return error_response('state must be active or final', 400)
    limit = request.args.get('limit', default=20, type=int) or 20
    limit = max(1, min(limit, LIST_LIMIT_MAX))
    rows = jobs.list_jobs(kinds, state or None, limit)
    return success_response(data=[jobs.public_view(r, with_result=False) for r in rows])


def _visible(job_id):
    row = jobs.get_job(job_id)
    if row is None or not _readable(row['kind']):
        return None
    return row


def _held_view(job_id):
    """A restore's view from its local state, when its SQLite transaction holds the database."""
    from services.jobs import restore as restore_job
    view = restore_job.local_view(job_id)
    if view is None or not _readable(view.get('kind')):
        return None
    return view


@bp.route('/api/v2/system/jobs/<job_id>', methods=['GET'])
@require_auth()
def get_job(job_id):
    from sqlalchemy.exc import OperationalError
    try:
        row = _visible(job_id)
    except OperationalError:
        db.session.rollback()
        view = _held_view(job_id)
        if view is None:
            raise
        return success_response(data=view)
    if row is None:
        return error_response('Job not found', 404)
    return success_response(data=jobs.public_view(row))


@bp.route('/api/v2/system/jobs/<job_id>/cancel', methods=['POST'])
@require_auth()
def cancel_job(job_id):
    """A pending job ends at once; a running one stops at its next check."""
    from sqlalchemy.exc import OperationalError
    try:
        row = _visible(job_id)
    except OperationalError:
        db.session.rollback()
        row = _held_view(job_id)
    if row is None:
        return error_response('Job not found', 404)
    try:
        outcome = jobs.request_cancellation(job_id)
    except Exception as e:
        logger.error(f"Job {job_id} not cancelled: {type(e).__name__}")
        return error_response('Job not cancelled', 500)
    if outcome == 'final':
        return error_response('The job has already ended', 409)
    if outcome == 'too_late':
        from services.jobs.restore import TOO_LATE
        return error_response(TOO_LATE, 409)
    message = 'Job cancelled' if outcome == 'cancelled' else 'Cancellation requested'
    view = _held_view(job_id)
    if view is not None:
        return success_response(data={**view, 'cancel_requested': True}, message=message)
    row = jobs.get_job(job_id)
    return success_response(data=jobs.public_view(row), message=message)
