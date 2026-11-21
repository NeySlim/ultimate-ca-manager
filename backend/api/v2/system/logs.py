"""System log access: the diagnostic bundle download, and reading the tail of
the application log for the log viewer.

The bundle returns a ZIP of the most relevant UCM logs (ucm.log, error.log,
access.log, the last lines of the systemd journal when running under systemd)
plus a small secret-free ``system.txt`` diagnostic. The reader returns the same
application log as records. Sensitive tokens are redacted on both paths, and
both are admin-only (``admin:system``).
"""
from . import bp

import logging

from auth.unified import require_auth
from flask import Response, request
from services.audit_service import AuditService
from services.log_bundle import build_bundle, bundle_filename
from services.log_reader import (DEFAULT_LEVEL, DEFAULT_LINES, LEVELS, MAX_LINES,
                                 SOURCES, read)
from utils.response import error_response, success_response
from utils.sanitize import content_disposition
from utils.trusted_proxy import client_ip

logger = logging.getLogger(__name__)


@bp.route('/api/v2/system/logs/bundle', methods=['GET'])
@require_auth(['admin:system'])
def download_log_bundle():
    """Download a diagnostic log bundle (ZIP)."""
    try:
        data = build_bundle()
    except Exception as exc:  # noqa: BLE001
        logger.error('Log bundle build failed: %s', exc)
        return error_response('Failed to build log bundle', 500)

    AuditService.log_action(
        action='log_bundle_downloaded',
        resource_type='system',
        resource_name='Log bundle',
        details=f'Log bundle downloaded from {client_ip()}',
        success=True,
    )

    return Response(
        data,
        mimetype='application/zip',
        headers={
            'Content-Disposition': content_disposition(bundle_filename()),
            'Cache-Control': 'no-store, no-cache, must-revalidate, private',
            'Pragma': 'no-cache',
            'X-Content-Type-Options': 'nosniff',
        },
    )


@bp.route('/api/v2/system/logs', methods=['GET'])
@require_auth(['admin:system'])
def read_application_log():
    """Read the tail of one log source as filtered records.

    ``q`` and ``exclude`` are case-insensitive substrings, matched against the
    message and the component name. They are not patterns: this process serves
    every protocol UCM speaks from a single gevent worker, and a caller's
    regular expression is unbounded work no timeout here can interrupt. A
    request carrying ``regex`` is refused rather than answered as a substring.
    """
    try:
        lines = int(request.args.get('lines', DEFAULT_LINES))
    except (TypeError, ValueError):
        return error_response('lines must be an integer', 400)
    if lines < 1 or lines > MAX_LINES:
        return error_response(f'lines must be between 1 and {MAX_LINES}', 400)

    # A floor, and INFO by default: the same one the page opens on and the
    # help describes. Absent, it used to mean no floor at all, so a caller who
    # omitted it read a different log from the one described to them.
    level = request.args.get('level') or DEFAULT_LEVEL
    if level.upper() not in LEVELS:
        return error_response(f'level must be one of {", ".join(LEVELS)}', 400)

    source = request.args.get('source') or 'app'
    if source not in SOURCES:
        return error_response(f'source must be one of {", ".join(SOURCES)}', 400)

    # Refused, not ignored. The parameter existed only between two commits of
    # this feature and no release ever answered it, so anything sending it is
    # asking for a pattern search that is not here, and silently giving it a
    # substring search would answer a different question than the one asked.
    if request.args.get('regex') is not None:
        return error_response('regex is not supported: q and exclude are substrings', 400)

    try:
        data = read(lines=lines, level=level, query=request.args.get('q'),
                    source=source, logger=request.args.get('component'),
                    since=request.args.get('since'), until=request.args.get('until'),
                    exclude=request.args.get('exclude'))
    except OSError as exc:
        logger.error('Application log read failed: %s', exc)
        return error_response('Failed to read the application log', 500)

    # Deliberately not audited, unlike the bundle download. AuditService echoes
    # every entry to the application logger, so auditing a read of that log
    # writes a line into the log being read — which the next read shows, for
    # ever. Following a log polls, so the viewer would bury the lines it exists
    # to surface under a record of itself. The bundle download stays audited:
    # it is rare, deliberate, and leaves with a copy of the file.
    return success_response(data=data)
