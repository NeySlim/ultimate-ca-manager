"""Discussion #207 batch-2: cert metadata, template_name, CA validity >20y."""
from datetime import datetime, timedelta, timezone

import pytest

from models import db, Certificate
from models.certificate_template import CertificateTemplate
from tests.conftest import get_json, assert_success


def test_patch_certificate_description_and_friendly_name(app, auth_client, create_cert):
    cert = create_cert(cn="meta.example.test")
    cert_id = cert["id"]
    r = auth_client.patch(
        f"/api/v2/certificates/{cert_id}",
        json={
            "description": "Updated description",
            "friendly_name": "OCSP — Lab CA",
        },
    )
    assert_success(r)
    data = get_json(r).get("data") or get_json(r)
    assert data["descr"] == "Updated description"
    assert data["friendly_name"] == "OCSP — Lab CA"
    assert data.get("description") == "Updated description"

    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        assert row.descr == "Updated description"
        assert row.friendly_name == "OCSP — Lab CA"


def test_patch_certificate_clear_friendly_name(app, auth_client, create_cert):
    cert = create_cert(cn="clear-fn.example.test")
    cert_id = cert["id"]
    with app.app_context():
        row = db.session.get(Certificate, cert_id)
        row.friendly_name = "tmp"
        db.session.commit()

    r = auth_client.patch(
        f"/api/v2/certificates/{cert_id}",
        json={"friendly_name": ""},
    )
    assert_success(r)
    data = get_json(r).get("data") or get_json(r)
    assert data["friendly_name"] is None


def test_certificate_to_dict_includes_template_name(app, create_cert):
    cert = create_cert(cn="tpl.example.test")
    with app.app_context():
        tpl = CertificateTemplate(
            name="Web SHA384",
            description="t",
            template_type="web_server",
            key_type="RSA-2048",
            validity_days=30,
            digest="sha384",
            dn_template='{"CN":"{hostname}"}',
            extensions_template="{}",
            is_active=True,
            created_by="test",
        )
        db.session.add(tpl)
        db.session.flush()
        row = db.session.get(Certificate, cert["id"])
        row.template_id = tpl.id
        db.session.commit()
        d = row.to_dict()
        assert d["template_id"] == tpl.id
        assert d["template_name"] == "Web SHA384"


def test_create_ca_validity_years_above_20(auth_client):
    r = auth_client.post(
        "/api/v2/cas",
        json={
            "commonName": "Lab Long Root",
            "description": "lab",
            "keyAlgo": "RSA",
            "keySize": 2048,
            "validityYears": 40,
            "type": "root",
            "country": "US",
            "organization": "Lab",
        },
    )
    assert r.status_code in (200, 201), r.get_data(as_text=True)
    data = get_json(r).get("data") or get_json(r)
    valid_to = data.get("valid_to") or data.get("not_valid_after")
    assert valid_to
    end = datetime.fromisoformat(str(valid_to).replace("Z", "+00:00"))
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    delta_years = (end - datetime.now(timezone.utc)).days / 365.0
    assert 38 <= delta_years <= 42


def test_create_ca_validity_end_date(auth_client):
    end = (datetime.now(timezone.utc) + timedelta(days=365 * 35)).date().isoformat()
    r = auth_client.post(
        "/api/v2/cas",
        json={
            "commonName": "Lab Date Root",
            "description": "lab",
            "keyAlgo": "RSA",
            "keySize": 2048,
            "validityYears": 10,
            "validityEndDate": end,
            "type": "root",
            "country": "US",
            "organization": "Lab",
        },
    )
    assert r.status_code in (200, 201), r.get_data(as_text=True)


def test_patch_certificate_requires_write(client, create_cert, auth_client):
    cert = create_cert(cn="authz.example.test")
    r = client.patch(
        f"/api/v2/certificates/{cert['id']}",
        json={"description": "nope"},
    )
    assert r.status_code in (401, 403)


def test_ca_protocol_http_rewrites_cdp_ocsp_urls(auth_client, create_ca, monkeypatch):
    ca = create_ca(cn="Proto HTTP CA")
    ca_id = ca["id"]

    import api.v2.cas.crud as cas_crud

    def _base(prefer_http=True, ca=None):
        # Signature used by both get_protocol_base_url and get_protocol_base_url_for_ca wrappers
        if ca is not None:
            prefer_http = True if getattr(ca, "protocol_http", None) is None else bool(ca.protocol_http)
        return "http://proto.test:8080" if prefer_http else "https://admin.test:8443"

    monkeypatch.setattr(cas_crud, "get_protocol_base_url_for_ca", lambda ca=None: _base(ca=ca))
    monkeypatch.setattr(
        cas_crud,
        "apply_protocol_urls_for_ca",
        lambda ca: (
            ca.set_cdp_urls([f"{_base(ca=ca)}/cdp/{ca.refid}.crl"]) if ca.cdp_enabled else None,
            ca.set_ocsp_urls([f"{_base(ca=ca)}/ocsp"]) if ca.ocsp_enabled else None,
        ),
    )

    r = auth_client.patch(
        f"/api/v2/cas/{ca_id}",
        json={"cdp_enabled": True, "ocsp_enabled": True, "protocol_http": True},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    data = get_json(r).get("data") or get_json(r)
    assert data.get("protocol_http") is True
    assert (data.get("cdp_urls") or [""])[0].startswith("http://")
    assert "/cdp/" in (data.get("cdp_urls") or [""])[0]
    assert (data.get("ocsp_urls") or [""])[0].startswith("http://")

    r = auth_client.patch(
        f"/api/v2/cas/{ca_id}",
        json={"protocol_http": False},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    data = get_json(r).get("data") or get_json(r)
    assert data.get("protocol_http") is False
    assert (data.get("cdp_urls") or [""])[0].startswith("https://admin.test:8443/cdp/")
    assert (data.get("ocsp_urls") or [""])[0].startswith("https://admin.test:8443/ocsp")
