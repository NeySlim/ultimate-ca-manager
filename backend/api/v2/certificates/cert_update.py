"""PATCH certificate metadata (description, friendly_name)."""
import logging

from flask import request, g
from auth.unified import require_auth
from utils.response import success_response, error_response
from models import Certificate, db
from utils.db_transaction import safe_commit
from . import bp

logger = logging.getLogger(__name__)

_MAX_DESCR = 255
_MAX_FRIENDLY = 255


@bp.route("/api/v2/certificates/<int:cert_id>", methods=["PATCH"])
@require_auth(["write:certificates"])
def update_certificate(cert_id):
    """Update editable certificate metadata.

    Body (all optional):
      description / descr — display description (max 255)
      friendly_name — operator label independent of CN (max 255, empty clears)
    """
    cert = db.session.get(Certificate, cert_id)
    if not cert:
        return error_response("Certificate not found", 404)

    data = request.json or {}
    if not isinstance(data, dict):
        return error_response("Invalid JSON body", 400)

    changed = []

    if "description" in data or "descr" in data:
        raw = data["description"] if "description" in data else data["descr"]
        if raw is None:
            return error_response("description cannot be null", 400)
        if not isinstance(raw, str):
            return error_response("description must be a string", 400)
        descr = raw.strip()
        if not descr:
            return error_response("description cannot be empty", 400)
        if len(descr) > _MAX_DESCR:
            return error_response(f"description too long (max {_MAX_DESCR})", 400)
        if descr != cert.descr:
            cert.descr = descr
            changed.append("descr")

    if "friendly_name" in data:
        raw = data["friendly_name"]
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            new_fn = None
        elif not isinstance(raw, str):
            return error_response("friendly_name must be a string", 400)
        else:
            new_fn = raw.strip()
            if len(new_fn) > _MAX_FRIENDLY:
                return error_response(
                    f"friendly_name too long (max {_MAX_FRIENDLY})", 400
                )
        if new_fn != cert.friendly_name:
            cert.friendly_name = new_fn
            changed.append("friendly_name")

    if not changed:
        return success_response(data=cert.to_dict(), message="No changes")

    ok, err = safe_commit(logger, "Failed to update certificate")
    if not ok:
        return error_response(err or "Failed to update certificate", 500)

    username = getattr(getattr(g, "current_user", None), "username", None) or getattr(
        getattr(g, "user", None), "username", "system"
    )
    logger.info(
        "Certificate %s metadata updated by %s: %s",
        cert_id,
        username,
        ",".join(changed),
    )
    return success_response(data=cert.to_dict(), message="Certificate updated")
