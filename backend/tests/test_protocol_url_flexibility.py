"""Unit + API tests for flexible per-CA protocol URL modes (#207)."""
from tests.conftest import get_json


def test_protocol_mode_inherit_and_https_admin(auth_client, create_ca, monkeypatch):
    ca = create_ca(cn="Mode Inherit CA")
    ca_id = ca["id"]

    import api.v2.cas.crud as cas_crud
    import utils.protocol_url as purl

    monkeypatch.setattr(
        purl, "get_protocol_base_url", lambda prefer_http=True: (
            "http://proto.test:8080" if prefer_http else "https://admin.test:8443"
        )
    )
    monkeypatch.setattr(purl, "get_https_admin_base_url", lambda: "https://admin.test:8443")
    monkeypatch.setattr(
        cas_crud, "get_protocol_base_url_for_ca",
        lambda ca=None: purl.get_protocol_base_url_for_ca(ca),
    )
    # Use real apply with patched resolvers
    monkeypatch.setattr(cas_crud, "apply_protocol_urls_for_ca", purl.apply_protocol_urls_for_ca)

    r = auth_client.patch(
        f"/api/v2/cas/{ca_id}",
        json={"cdp_enabled": True, "ocsp_enabled": True, "protocol_mode": "inherit"},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    data = get_json(r).get("data") or get_json(r)
    assert data.get("protocol_mode") == "inherit"
    assert data.get("protocol_http") is True
    assert (data.get("cdp_urls") or [""])[0].startswith("http://proto.test:8080/cdp/")

    r = auth_client.patch(
        f"/api/v2/cas/{ca_id}",
        json={"protocol_mode": "https_admin"},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    data = get_json(r).get("data") or get_json(r)
    assert data.get("protocol_mode") == "https_admin"
    assert data.get("protocol_http") is False
    assert (data.get("cdp_urls") or [""])[0].startswith("https://admin.test:8443/cdp/")


def test_protocol_mode_custom_and_endpoint_overrides(auth_client, create_ca, monkeypatch):
    ca = create_ca(cn="Mode Custom CA")
    ca_id = ca["id"]

    import api.v2.cas.crud as cas_crud
    import utils.protocol_url as purl

    monkeypatch.setattr(
        purl, "get_protocol_base_url", lambda prefer_http=True: "http://settings.test:8080"
    )
    monkeypatch.setattr(purl, "get_https_admin_base_url", lambda: "https://admin.test:8443")
    monkeypatch.setattr(cas_crud, "apply_protocol_urls_for_ca", purl.apply_protocol_urls_for_ca)

    r = auth_client.patch(
        f"/api/v2/cas/{ca_id}",
        json={
            "cdp_enabled": True,
            "ocsp_enabled": True,
            "aia_ca_issuers_enabled": True,
            "protocol_mode": "custom",
            "protocol_base_url_override": "http://pki-lab.example:8080",
        },
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    data = get_json(r).get("data") or get_json(r)
    assert data.get("protocol_mode") == "custom"
    assert data.get("protocol_base_url_override") == "http://pki-lab.example:8080"
    assert (data.get("cdp_urls") or [""])[0].startswith("http://pki-lab.example:8080/cdp/")
    assert (data.get("ocsp_urls") or [""])[0] == "http://pki-lab.example:8080/ocsp"

    r = auth_client.patch(
        f"/api/v2/cas/{ca_id}",
        json={
            "cdp_base_url": "http://crl.example:8080",
            "ocsp_base_url": "http://ocsp.example:8080",
            "aia_base_url": "http://aia.example:8080",
        },
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    data = get_json(r).get("data") or get_json(r)
    assert (data.get("cdp_urls") or [""])[0].startswith("http://crl.example:8080/cdp/")
    assert (data.get("ocsp_urls") or [""])[0] == "http://ocsp.example:8080/ocsp"
    assert (data.get("aia_ca_issuers_urls") or [""])[0].startswith("http://aia.example:8080/ca/")


def test_protocol_mode_custom_requires_override(auth_client, create_ca):
    ca = create_ca(cn="Custom Empty CA")
    r = auth_client.patch(
        f"/api/v2/cas/{ca['id']}",
        json={"protocol_mode": "custom"},
    )
    assert r.status_code == 400


def test_legacy_protocol_http_still_works(auth_client, create_ca, monkeypatch):
    ca = create_ca(cn="Legacy Bool CA")
    ca_id = ca["id"]

    import api.v2.cas.crud as cas_crud
    import utils.protocol_url as purl

    monkeypatch.setattr(
        purl, "get_protocol_base_url", lambda prefer_http=True: (
            "http://proto.test:8080" if prefer_http else "https://admin.test:8443"
        )
    )
    monkeypatch.setattr(purl, "get_https_admin_base_url", lambda: "https://admin.test:8443")
    monkeypatch.setattr(cas_crud, "apply_protocol_urls_for_ca", purl.apply_protocol_urls_for_ca)

    r = auth_client.patch(
        f"/api/v2/cas/{ca_id}",
        json={"cdp_enabled": True, "protocol_http": False},
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    data = get_json(r).get("data") or get_json(r)
    assert data.get("protocol_mode") == "https_admin"
    assert data.get("protocol_http") is False


def test_validate_protocol_base_override_unit():
    from utils.protocol_url import validate_protocol_base_override

    ok, err = validate_protocol_base_override("http://pki.example:8080")
    assert err is None and ok == "http://pki.example:8080"

    ok, err = validate_protocol_base_override("http://localhost:8080")
    assert ok is None and err and "localhost" in err

    ok, err = validate_protocol_base_override("http://pki.example:8080/cdp")
    assert ok is None and err and "path" in err.lower()

    ok, err = validate_protocol_base_override("ftp://pki.example")
    assert ok is None and err

    ok, err = validate_protocol_base_override("")
    assert ok is None and err is None
