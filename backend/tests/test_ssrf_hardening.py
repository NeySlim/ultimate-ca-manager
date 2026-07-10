"""Regression tests for SSRF hardening:
  #6 safe_request_get/post must send a default request timeout (never hang forever).
  #5 the ACME-proxy connection test must fetch via the pinned safe_request_get
     (DNS-rebinding-safe), not a bare urllib.urlopen that re-resolves the hostname.
"""


# ---- #6: default timeout on the SSRF-safe request wrappers ----
def test_safe_request_get_defaults_timeout(monkeypatch):
    import requests
    from utils import ssrf_protection
    cap = {}
    monkeypatch.setattr(requests, "get", lambda url, **kw: cap.update(kw) or "ok")
    ssrf_protection.safe_request_get("https://93.184.216.34/")   # literal IP → no DNS
    assert cap.get("timeout") == 30


def test_safe_request_get_preserves_explicit_timeout(monkeypatch):
    import requests
    from utils import ssrf_protection
    cap = {}
    monkeypatch.setattr(requests, "get", lambda url, **kw: cap.update(kw) or "ok")
    ssrf_protection.safe_request_get("https://93.184.216.34/", timeout=5)
    assert cap.get("timeout") == 5


def test_safe_request_post_defaults_timeout(monkeypatch):
    import requests
    from utils import ssrf_protection
    cap = {}
    monkeypatch.setattr(requests, "post", lambda url, **kw: cap.update(kw) or "ok")
    ssrf_protection.safe_request_post("https://93.184.216.34/")
    assert cap.get("timeout") == 30


# ---- #5: ACME proxy uses the pinned safe_request_get ----
def test_proxy_connection_uses_pinned_safe_request(auth_client, monkeypatch):
    import api.v2.acme_client.proxy as proxy_mod

    called = {}

    class _Resp:
        def json(self):
            return {"meta": {"website": "https://ca.example"}, "newNonce": "https://ca/n"}

    def fake_get(url, **kw):
        called["url"] = url
        called["kw"] = kw
        return _Resp()

    monkeypatch.setattr(proxy_mod, "safe_request_get", fake_get)
    r = auth_client.post("/api/v2/acme/client/proxy/test-connection",
                         json={"url": "https://93.184.216.34/directory"})
    assert r.status_code == 200
    assert called.get("url") == "https://93.184.216.34/directory"   # pinned path was used
    assert called["kw"].get("timeout") == 10
