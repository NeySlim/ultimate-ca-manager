"""The ACME proxy passes nothing of the upstream alternates, nor of UCM's own, to its client (#220, #400)."""
import json
from types import SimpleNamespace

import pytest

from models import db
from models.acme_models import AcmeClientOrder
from tests.test_acme_proxy_issue_fixes import UPSTREAM, _b64, _make_service, _self_signed_pem, _seed_proxy_order

CERT_URL = f'{UPSTREAM}/cert/chain-1'


@pytest.fixture
def proxy_route(app, monkeypatch):
    import api.acme.acme_proxy_api as proxy_api
    from services.cert_service import CertificateService
    pem = _self_signed_pem()
    upstream = SimpleNamespace(
        status_code=200, content=pem.encode(),
        headers={'Link': [f'<{UPSTREAM}/cert/chain-1/1>;rel="alternate"', f'<{UPSTREAM}/dir>;rel="index"'],
                 'Content-Type': 'application/pem-certificate-chain'})
    with app.app_context():
        svc = _make_service(app)
        _seed_proxy_order(upstream_order_url=f'{UPSTREAM}/order/9', certificate_url=CERT_URL)
        monkeypatch.setattr(svc, '_post_with_account', lambda *_a, **_k: upstream)
        monkeypatch.setattr(CertificateService, 'import_certificate',
                            staticmethod(lambda **_kw: SimpleNamespace(id=4343)))
        monkeypatch.setattr(proxy_api, 'get_proxy_service', lambda slug=None: svc)
        monkeypatch.setattr(proxy_api, 'verify_proxy_jws', lambda: (True, {}, None, None))
        monkeypatch.setattr(proxy_api, '_requester_identity', lambda jwk=None: (None, None))
        yield pem
        AcmeClientOrder.query.filter_by(domains=json.dumps(['proxy-fix.test'])).delete()
        db.session.commit()


def test_the_proxy_response_carries_no_link_and_no_alternate(client, proxy_route):
    r = client.post(f'/acme/proxy/cert/{_b64(CERT_URL)}', data='{}', content_type='application/jose+json')
    assert r.status_code == 200, r.data
    assert r.headers.getlist('Link') == []
    assert '/alt/' not in r.get_data(as_text=True)
    assert proxy_route.strip() in r.get_data(as_text=True)
