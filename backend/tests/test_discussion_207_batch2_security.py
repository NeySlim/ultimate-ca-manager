"""Security / authz gates for discussion #207 batch-2 APIs."""
from tests.conftest import get_json


def test_patch_certificate_requires_auth(client, create_cert):
    cert = create_cert(cn="sec-unauth.example.test")
    r = client.patch(
        f"/api/v2/certificates/{cert['id']}",
        json={"description": "nope"},
    )
    assert r.status_code in (401, 403)


def test_patch_certificate_rejects_empty_description(auth_client, create_cert):
    cert = create_cert(cn="sec-empty.example.test")
    r = auth_client.patch(
        f"/api/v2/certificates/{cert['id']}",
        json={"description": "   "},
    )
    assert r.status_code == 400


def test_patch_certificate_rejects_oversized_fields(auth_client, create_cert):
    cert = create_cert(cn="sec-big.example.test")
    r = auth_client.patch(
        f"/api/v2/certificates/{cert['id']}",
        json={"description": "x" * 300},
    )
    assert r.status_code == 400
    r = auth_client.patch(
        f"/api/v2/certificates/{cert['id']}",
        json={"friendly_name": "y" * 300},
    )
    assert r.status_code == 400


def test_patch_certificate_rejects_non_string_friendly_name(auth_client, create_cert):
    cert = create_cert(cn="sec-type.example.test")
    r = auth_client.patch(
        f"/api/v2/certificates/{cert['id']}",
        json={"friendly_name": 12345},
    )
    assert r.status_code == 400


def test_protocol_http_requires_auth(client, create_ca):
    ca = create_ca(cn="Sec Proto CA")
    r = client.patch(
        f"/api/v2/cas/{ca['id']}",
        json={"protocol_http": False},
    )
    assert r.status_code in (401, 403)


def test_protocol_http_viewer_forbidden(viewer_client, create_ca):
    ca = create_ca(cn="Sec Proto Viewer CA")
    r = viewer_client.patch(
        f"/api/v2/cas/{ca['id']}",
        json={"protocol_http": False},
    )
    # viewer may lack write:cas — expect 403 (or 401 if session odd)
    assert r.status_code in (401, 403)


def test_ca_validity_rejects_over_100_years(auth_client):
    r = auth_client.post(
        "/api/v2/cas",
        json={
            "commonName": "Too Long Root",
            "keyAlgo": "RSA",
            "keySize": 2048,
            "validityYears": 101,
            "type": "root",
            "country": "US",
            "organization": "Lab",
        },
    )
    assert r.status_code == 400
    body = get_json(r)
    msg = str(body.get("message") or body.get("error") or body).lower()
    assert "100" in msg or "validity" in msg


def test_ca_validity_end_date_past_rejected(auth_client):
    r = auth_client.post(
        "/api/v2/cas",
        json={
            "commonName": "Past End Root",
            "keyAlgo": "RSA",
            "keySize": 2048,
            "validityYears": 10,
            "validityEndDate": "2000-01-01",
            "type": "root",
            "country": "US",
            "organization": "Lab",
        },
    )
    assert r.status_code == 400
