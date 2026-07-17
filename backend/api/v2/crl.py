"""
CRL & OCSP Routes v2.0
"""

import logging

from auth.unified import require_auth
from flask import Blueprint, g, request
from models import CA, AuditLog, db
from models.crl import CRLMetadata
from services.audit_service import AuditService
from services.crl_service import CRLService
from utils.db_transaction import safe_commit
from utils.protocol_url import get_protocol_base_url_for_ca
from utils.response import error_response, success_response
from utils.trusted_proxy import client_ip

logger = logging.getLogger(__name__)

bp = Blueprint("crl_v2", __name__)


@bp.route("/api/v2/crl", methods=["GET"])
@require_auth(["read:crl"])
def list_crls():
    """List CRLs - returns latest base (full) CRL per CA"""
    from sqlalchemy import func

    # Get the latest base CRL for each CA (exclude delta CRLs)
    subquery = (
        db.session.query(
            CRLMetadata.ca_id, func.max(CRLMetadata.crl_number).label("max_crl_number")
        )
        .filter(CRLMetadata.is_delta == False)
        .group_by(CRLMetadata.ca_id)
        .subquery()
    )

    crls = CRLMetadata.query.join(
        subquery,
        db.and_(
            CRLMetadata.ca_id == subquery.c.ca_id,
            CRLMetadata.crl_number == subquery.c.max_crl_number,
        ),
    ).all()

    # Batch-load delta CRLs to avoid N+1
    ca_ids = [crl.ca_id for crl in crls]
    delta_subq = (
        db.session.query(
            CRLMetadata.ca_id, func.max(CRLMetadata.crl_number).label("max_num")
        )
        .filter(CRLMetadata.ca_id.in_(ca_ids), CRLMetadata.is_delta == True)
        .group_by(CRLMetadata.ca_id)
        .subquery()
    )

    deltas = (
        CRLMetadata.query.join(
            delta_subq,
            db.and_(
                CRLMetadata.ca_id == delta_subq.c.ca_id,
                CRLMetadata.crl_number == delta_subq.c.max_num,
            ),
        ).all()
        if ca_ids
        else []
    )
    delta_map = {d.ca_id: d for d in deltas}

    result = []
    for crl in crls:
        data = crl.to_dict()
        if crl.ca:
            data["caref"] = crl.ca.refid
        if crl.ca_id in delta_map:
            data["delta_crl"] = delta_map[crl.ca_id].to_dict()
        result.append(data)

    return success_response(data=result)


@bp.route("/api/v2/crl/<int:ca_id>", methods=["GET"])
@require_auth(["read:crl"])
def get_crl(ca_id):
    """Get CRL for CA"""
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response("CA not found", 404)

    crl = (
        CRLMetadata.query.filter_by(ca_id=ca_id, is_delta=False)
        .order_by(CRLMetadata.crl_number.desc())
        .first()
    )
    if not crl:
        return success_response(data=None)

    data = crl.to_dict(include_crl_data=True)
    data["caref"] = ca.refid
    return success_response(data=data)


@bp.route("/api/v2/crl/<int:ca_id>/regenerate", methods=["POST"])
@require_auth(["write:crl"])
def regenerate_crl(ca_id):
    """Force CRL regeneration"""
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response("CA not found", 404)

    # Check if CA has private key
    if not ca.has_private_key:
        return error_response(
            f'CA "{ca.descr}" does not have a private key - cannot sign CRL', 400
        )

    # Check offline status
    if ca.offline:
        return error_response(
            f"Cannot regenerate CRL: CA '{ca.descr}' is offline ({ca.offline_reason or 'no reason provided'})",
            400,
        )

    try:
        crl_metadata = CRLService.generate_crl(
            ca.id,
            username=(
                getattr(g, "user", {}).get("username", "admin")
                if hasattr(g, "user")
                else "admin"
            ),
        )

        AuditService.log_action(
            action="crl_regenerate",
            resource_type="crl",
            resource_id=str(ca_id),
            resource_name=ca.descr,
            details=f"Regenerated CRL for CA: {ca.descr}",
            success=True,
        )

        data = crl_metadata.to_dict() if crl_metadata else None
        if data:
            data["caref"] = ca.refid

        try:
            from websocket.emitters import on_crl_regenerated

            on_crl_regenerated(
                ca_id,
                ca.descr,
                data.get("next_update", "") if data else "",
                data.get("entries_count", 0) if data else 0,
            )
        except Exception:
            pass

        return success_response(data=data, message="CRL regenerated successfully")
    except Exception as e:
        logger.error(f"Failed to regenerate CRL: {e}")
        return error_response("Failed to regenerate CRL", 500)


@bp.route("/api/v2/crl/<int:ca_id>/auto-regen", methods=["POST"])
@require_auth(["write:crl"])
def toggle_auto_regen(ca_id):
    """Enable/disable automatic CRL regeneration for a CA"""
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response("CA not found", 404)

    data = request.get_json() or {}
    enabled = data.get("enabled", not ca.cdp_enabled)  # Toggle if not specified

    try:
        ca.cdp_enabled = enabled

        # Auto-generate CDP URL if enabling and no URLs configured
        primary_cdp = ca.get_primary_cdp_url()
        if enabled and (not primary_cdp or primary_cdp.startswith("https://")):
            base_url = get_protocol_base_url_for_ca(ca)
            if not base_url:
                return error_response(
                    "Cannot auto-generate CDP URL: configure a FQDN or Protocol Base URL in Settings first",
                    400,
                )
            ca.set_cdp_urls([f"{base_url}/cdp/{ca.refid}.crl"])

        # Audit log
        username = (
            getattr(g, "user", {}).get("username", "admin")
            if hasattr(g, "user")
            else "admin"
        )
        audit = AuditLog(
            action="crl_auto_regen_toggle",
            resource_type="ca",
            resource_id=str(ca.id),
            resource_name=ca.descr,
            username=username,
            details=f"{'Enabled' if enabled else 'Disabled'} automatic CRL regeneration",
            ip_address=client_ip(),
            success=True,
        )
        db.session.add(audit)
        ok, err = safe_commit(logger, "Failed to update CRL settings")
        if not ok:
            return err

        return success_response(
            data=ca.to_dict(),
            message=f"Automatic CRL regeneration {'enabled' if enabled else 'disabled'}",
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to update CRL auto-regen setting: {e}")
        return error_response("Failed to update CRL settings", 500)


@bp.route("/api/v2/crl/<int:ca_id>/delta", methods=["GET"])
@require_auth(["read:crl"])
def get_delta_crl(ca_id):
    """Get latest delta CRL for a CA"""
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response("CA not found", 404)

    delta = CRLService.get_latest_delta_crl(ca_id)
    if not delta:
        return success_response(data=None)

    data = delta.to_dict(include_crl_data=True)
    data["caref"] = ca.refid
    return success_response(data=data)


@bp.route("/api/v2/crl/<int:ca_id>/delta/regenerate", methods=["POST"])
@require_auth(["write:crl"])
def regenerate_delta_crl(ca_id):
    """Force delta CRL generation"""
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response("CA not found", 404)
    if not ca.has_private_key:
        return error_response("CA does not have a private key", 400)
    if not ca.cdp_enabled:
        return error_response("CDP is not enabled for this CA", 400)
    if not ca.delta_crl_enabled:
        return error_response("Delta CRL is not enabled for this CA", 400)

    try:
        username = (
            getattr(g, "user", {}).get("username", "admin")
            if hasattr(g, "user")
            else "admin"
        )
        crl_metadata = CRLService.generate_delta_crl(ca.id, username=username)

        data = crl_metadata.to_dict() if crl_metadata else None
        if data:
            data["caref"] = ca.refid

        return success_response(data=data, message="Delta CRL generated successfully")
    except ValueError as e:
        logger.warning(f"Delta CRL generation rejected for CA {ca_id}: {e}")
        msg = str(e)
        if "not found" in msg:
            return error_response("CA not found", 404)
        elif "private key" in msg:
            return error_response("CA does not have a private key", 400)
        elif "base CRL" in msg:
            return error_response("No base CRL exists — generate a full CRL first", 400)
        return error_response("Delta CRL generation failed", 400)
    except Exception as e:
        logger.error(f"Failed to generate delta CRL: {e}")
        return error_response("Failed to generate delta CRL", 500)


@bp.route("/api/v2/crl/<int:ca_id>/delta-config", methods=["POST"])
@require_auth(["write:crl"])
def configure_delta_crl(ca_id):
    """Configure delta CRL settings for a CA"""
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response("CA not found", 404)

    data = request.get_json() or {}

    try:
        if "enabled" in data:
            ca.delta_crl_enabled = bool(data["enabled"])
        if "interval" in data:
            interval = int(data["interval"])
            if interval < 1 or interval > 168:  # 1h to 7 days
                return error_response("Interval must be between 1 and 168 hours", 400)
            ca.delta_crl_interval = interval

        username = (
            getattr(g, "user", {}).get("username", "admin")
            if hasattr(g, "user")
            else "admin"
        )
        AuditService.log_action(
            action="delta_crl_config",
            resource_type="ca",
            resource_id=str(ca.id),
            resource_name=ca.descr,
            details=f"Delta CRL config: enabled={ca.delta_crl_enabled}, interval={ca.delta_crl_interval}h",
            success=True,
        )

        ok, err = safe_commit(logger, "Failed to update delta CRL settings")
        if not ok:
            return err

        return success_response(
            data={
                "delta_crl_enabled": ca.delta_crl_enabled,
                "delta_crl_interval": ca.delta_crl_interval,
            },
            message="Delta CRL configuration updated",
        )
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to configure delta CRL: {e}")
        return error_response("Failed to update delta CRL settings", 500)


@bp.route("/api/v2/crl/<int:ca_id>/config", methods=["GET"])
@require_auth(["read:crl"])
def get_full_crl_config(ca_id):
    """Get full CRL validity / publish / digest settings (discussion #207)."""
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response("CA not found", 404)

    return success_response(
        data={
            "crl_validity_days": (
                ca.crl_validity_days if ca.crl_validity_days is not None else 7
            ),
            "crl_publish_interval_hours": (
                ca.crl_publish_interval_hours
                if ca.crl_publish_interval_hours is not None
                else 168
            ),
            "crl_digest": ca.crl_digest or "sha256",
            "delta_crl_enabled": bool(ca.delta_crl_enabled),
            "delta_crl_interval": ca.delta_crl_interval or 4,
        }
    )


@bp.route("/api/v2/crl/<int:ca_id>/config", methods=["POST"])
@require_auth(["write:crl"])
def configure_full_crl(ca_id):
    """Update full CRL validity / publish / digest settings (discussion #207)."""
    ca = db.session.get(CA, ca_id)
    if not ca:
        return error_response("CA not found", 404)

    data = request.get_json() or {}
    allowed_digests = {"sha224", "sha256", "sha384", "sha512"}

    try:
        if "crl_validity_days" in data:
            days = int(data["crl_validity_days"])
            if days < 1 or days > 365:
                return error_response(
                    "crl_validity_days must be between 1 and 365", 400
                )
            ca.crl_validity_days = days
        if "crl_publish_interval_hours" in data:
            hours = int(data["crl_publish_interval_hours"])
            if hours < 1 or hours > 8760:
                return error_response(
                    "crl_publish_interval_hours must be between 1 and 8760", 400
                )
            ca.crl_publish_interval_hours = hours
        if "crl_digest" in data:
            digest = str(data["crl_digest"]).lower().strip()
            if digest not in allowed_digests:
                return error_response(
                    f"crl_digest must be one of: {', '.join(sorted(allowed_digests))}",
                    400,
                )
            ca.crl_digest = digest

        AuditService.log_action(
            action="crl_config",
            resource_type="ca",
            resource_id=str(ca.id),
            resource_name=ca.descr,
            details=(
                f"CRL config: validity={ca.crl_validity_days}d, "
                f"publish={ca.crl_publish_interval_hours}h, digest={ca.crl_digest}"
            ),
            success=True,
        )

        ok, err = safe_commit(logger, "Failed to update CRL settings")
        if not ok:
            return err

        return success_response(
            data={
                "crl_validity_days": ca.crl_validity_days,
                "crl_publish_interval_hours": ca.crl_publish_interval_hours,
                "crl_digest": ca.crl_digest or "sha256",
            },
            message="CRL configuration updated",
        )
    except (TypeError, ValueError):
        db.session.rollback()
        return error_response("Invalid CRL configuration values", 400)
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to configure CRL: {e}")
        return error_response("Failed to update CRL settings", 500)


@bp.route("/api/v2/ocsp/status", methods=["GET"])
@require_auth(["read:certificates"])
def get_ocsp_status():
    """Get OCSP service status"""
    try:
        ocsp_cas = CA.query.filter_by(ocsp_enabled=True).count()
        enabled = ocsp_cas > 0
        return success_response(
            data={"enabled": enabled, "running": enabled, "ca_count": ocsp_cas}
        )
    except Exception as e:
        logger.warning(f"OCSP status check failed: {e}")
        return success_response(
            data={"enabled": False, "running": False, "ca_count": 0}
        )


@bp.route("/api/v2/ocsp/stats", methods=["GET"])
@require_auth(["read:certificates"])
def get_ocsp_stats():
    """Get OCSP statistics from cached responses"""
    from models.ocsp import OCSPResponse

    try:
        total = OCSPResponse.query.count()
        return success_response(
            data={
                "total_requests": total,
                "cache_hits": total,
            }
        )
    except Exception as e:
        logger.error(f"OCSP stats query failed: {e}")
        return success_response(
            data={
                "total_requests": 0,
                "cache_hits": 0,
            }
        )
