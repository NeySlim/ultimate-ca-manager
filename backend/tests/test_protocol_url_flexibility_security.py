"""Security / authz / validation gates for protocol URL flexibility."""
from tests.conftest import get_json


def test_protocol_mode_requires_auth(client, create_ca):
    ca = create_ca(cn="Sec Mode Unauth")
    r = client.patch(
        f"/api/v2/cas/{ca['id']}",
        json={"protocol_mode": "https_admin"},
    )
    assert r.status_code in (401, 403)


def test_protocol_mode_viewer_forbidden(viewer_client, create_ca):
    ca = create_ca(cn="Sec Mode Viewer")
    r = viewer_client.patch(
        f"/api/v2/cas/{ca['id']}",
        json={"protocol_mode": "https_admin"},
    )
    assert r.status_code in (401, 403)


def test_protocol_mode_rejects_unknown(auth_client, create_ca):
    ca = create_ca(cn="Sec Mode Bad")
    r = auth_client.patch(
        f"/api/v2/cas/{ca['id']}",
        json={"protocol_mode": "ftp_evil"},
    )
    assert r.status_code == 400
    msg = str(get_json(r).get("message") or "").lower()
    assert "protocol_mode" in msg


def test_override_rejects_localhost(auth_client, create_ca):
    ca = create_ca(cn="Sec Localhost")
    r = auth_client.patch(
        f"/api/v2/cas/{ca['id']}",
        json={
            "protocol_mode": "custom",
            "protocol_base_url_override": "http://127.0.0.1:8080",
        },
    )
    assert r.status_code == 400


def test_override_rejects_path_and_javascript(auth_client, create_ca):
    ca = create_ca(cn="Sec Path")
    r = auth_client.patch(
        f"/api/v2/cas/{ca['id']}",
        json={
            "protocol_mode": "custom",
            "protocol_base_url_override": "http://evil.example/cdp",
        },
    )
    assert r.status_code == 400

    r = auth_client.patch(
        f"/api/v2/cas/{ca['id']}",
        json={
            "protocol_mode": "custom",
            "protocol_base_url_override": "javascript:alert(1)",
        },
    )
    assert r.status_code == 400


def test_override_rejects_oversized(auth_client, create_ca):
    ca = create_ca(cn="Sec Big")
    r = auth_client.patch(
        f"/api/v2/cas/{ca['id']}",
        json={
            "protocol_mode": "custom",
            "protocol_base_url_override": "http://x.example/" + ("a" * 600),
        },
    )
    assert r.status_code == 400


def test_cdp_base_rejects_non_url_scheme(auth_client, create_ca):
    ca = create_ca(cn="Sec Cdp Scheme")
    r = auth_client.patch(
        f"/api/v2/cas/{ca['id']}",
        json={"cdp_base_url": "file:///etc/passwd"},
    )
    assert r.status_code == 400


def test_https_custom_allowed_but_documented(auth_client, create_ca, monkeypatch):
    """https:// overrides are allowed (operator choice) but not recommended."""
    ca = create_ca(cn="Sec Https Custom")
    import api.v2.cas.crud as cas_crud
    import utils.protocol_url as purl

    monkeypatch.setattr(cas_crud, "apply_protocol_urls_for_ca", purl.apply_protocol_urls_for_ca)
    r = auth_client.patch(
        f"/api/v2/cas/{ca['id']}",
        json={
            "cdp_enabled": True,
            "protocol_mode": "custom",
            "protocol_base_url_override": "https://cdn.example",
        },
    )
    assert r.status_code == 200, r.get_data(as_text=True)
    data = get_json(r).get("data") or get_json(r)
    assert data.get("protocol_base_url_override") == "https://cdn.example"
