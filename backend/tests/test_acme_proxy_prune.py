"""Tests for the ACME proxy "prune replaced certificates" option (#240).

Opt-in (acme.proxy.prune_replaced_certificates, default off): when a proxy
order finalizes, certificates imported by older proxy orders with the exact
same domain set are deleted. Revoked certificates and non-proxy-issued
certificates are never touched.
"""
import json
import uuid

import pytest

from models import db
from models.acme_models import AcmeClientOrder
from models.certificate import Certificate
from services.acme.acme_proxy_service import AcmeProxyService


DOMAINS = ['prune.test']


def _make_service():
    svc = AcmeProxyService('https://ucm.example/acme/proxy')
    return svc


def _set_prune(enabled: bool):
    from models import SystemConfig
    cfg = SystemConfig.query.filter_by(key='acme.proxy.prune_replaced_certificates').first()
    if cfg is None:
        cfg = SystemConfig(key='acme.proxy.prune_replaced_certificates', value='')
        db.session.add(cfg)
    cfg.value = 'true' if enabled else 'false'
    db.session.commit()


def _make_cert(descr, source='acme_client', revoked=False):
    cert = Certificate(
        refid=str(uuid.uuid4()),
        descr=descr,
        crt='-----BEGIN CERTIFICATE-----\nfake\n-----END CERTIFICATE-----',
        source=source,
        revoked=revoked,
    )
    db.session.add(cert)
    db.session.commit()
    return cert


def _make_proxy_order(domains=DOMAINS, cert_id=None):
    order = AcmeClientOrder(
        domains=json.dumps(domains),
        status='valid',
        is_proxy_order=True,
        certificate_id=cert_id,
    )
    db.session.add(order)
    db.session.commit()
    return order


@pytest.fixture(autouse=True)
def _clean(app):
    with app.app_context():
        yield
        AcmeClientOrder.query.delete()
        Certificate.query.filter(Certificate.descr.like('prune-%')).delete()
        from models import SystemConfig
        SystemConfig.query.filter_by(key='acme.proxy.prune_replaced_certificates').delete()
        db.session.commit()


class TestPruneFlag:
    def test_disabled_by_default(self, app):
        with app.app_context():
            assert AcmeProxyService._prune_replaced_certificates_enabled() is False

    def test_enabled_when_true(self, app):
        with app.app_context():
            _set_prune(True)
            assert AcmeProxyService._prune_replaced_certificates_enabled() is True

    def test_invalid_value_falls_back_disabled(self, app):
        from models import SystemConfig
        with app.app_context():
            db.session.add(SystemConfig(
                key='acme.proxy.prune_replaced_certificates', value='banana'))
            db.session.commit()
            assert AcmeProxyService._prune_replaced_certificates_enabled() is False


class TestPruneReplacedCertificates:
    def test_disabled_flag_keeps_old_cert(self, app):
        with app.app_context():
            _set_prune(False)
            old_cert = _make_cert('prune-old')
            _make_proxy_order(cert_id=old_cert.id)
            new_cert = _make_cert('prune-new')
            new_order = _make_proxy_order(cert_id=new_cert.id)

            svc = _make_service()
            pruned = svc._prune_replaced_certificates(new_order, new_cert.id)

            assert pruned == 0
            assert db.session.get(Certificate, old_cert.id) is not None

    def test_enabled_flag_deletes_superseded_proxy_cert(self, app):
        with app.app_context():
            _set_prune(True)
            old_cert = _make_cert('prune-old')
            old_order = _make_proxy_order(cert_id=old_cert.id)
            new_cert = _make_cert('prune-new')
            new_order = _make_proxy_order(cert_id=new_cert.id)

            svc = _make_service()
            pruned = svc._prune_replaced_certificates(new_order, new_cert.id)

            assert pruned == 1
            assert db.session.get(Certificate, old_cert.id) is None
            assert db.session.get(Certificate, new_cert.id) is not None
            # Order rows are detached, not deleted (FK safety)
            assert db.session.get(AcmeClientOrder, old_order.id).certificate_id is None

    def test_different_domains_are_kept(self, app):
        with app.app_context():
            _set_prune(True)
            other_cert = _make_cert('prune-other')
            _make_proxy_order(domains=['other.test'], cert_id=other_cert.id)
            new_cert = _make_cert('prune-new')
            new_order = _make_proxy_order(cert_id=new_cert.id)

            svc = _make_service()
            pruned = svc._prune_replaced_certificates(new_order, new_cert.id)

            assert pruned == 0
            assert db.session.get(Certificate, other_cert.id) is not None

    def test_revoked_certificate_is_kept(self, app):
        with app.app_context():
            _set_prune(True)
            revoked_cert = _make_cert('prune-revoked', revoked=True)
            _make_proxy_order(cert_id=revoked_cert.id)
            new_cert = _make_cert('prune-new')
            new_order = _make_proxy_order(cert_id=new_cert.id)

            svc = _make_service()
            pruned = svc._prune_replaced_certificates(new_order, new_cert.id)

            assert pruned == 0
            assert db.session.get(Certificate, revoked_cert.id) is not None

    def test_non_proxy_certificate_is_kept(self, app):
        with app.app_context():
            _set_prune(True)
            local_cert = _make_cert('prune-local', source='webui')
            _make_proxy_order(cert_id=local_cert.id)
            new_cert = _make_cert('prune-new')
            new_order = _make_proxy_order(cert_id=new_cert.id)

            svc = _make_service()
            pruned = svc._prune_replaced_certificates(new_order, new_cert.id)

            assert pruned == 0
            assert db.session.get(Certificate, local_cert.id) is not None

    def test_non_proxy_orders_do_not_trigger_prune(self, app):
        """Certs linked to non-proxy orders with the same domains are out of scope."""
        with app.app_context():
            _set_prune(True)
            client_cert = _make_cert('prune-client', source='acme_client')
            AcmeClientOrder.query.delete()
            db.session.commit()
            non_proxy = AcmeClientOrder(
                domains=json.dumps(DOMAINS),
                status='valid',
                is_proxy_order=False,
                certificate_id=client_cert.id,
            )
            db.session.add(non_proxy)
            db.session.commit()
            new_cert = _make_cert('prune-new')
            new_order = _make_proxy_order(cert_id=new_cert.id)

            svc = _make_service()
            pruned = svc._prune_replaced_certificates(new_order, new_cert.id)

            assert pruned == 0
            assert db.session.get(Certificate, client_cert.id) is not None


class TestSettingsRoundtrip:
    URL = '/api/v2/acme/client/settings'

    def test_patch_enables_and_get_reflects(self, auth_client):
        r = auth_client.patch(self.URL, json={'proxy_prune_replaced_certificates': True})
        assert r.status_code == 200
        body = auth_client.get(self.URL).get_json()['data']
        assert body['proxy_prune_replaced_certificates'] is True

        r = auth_client.patch(self.URL, json={'proxy_prune_replaced_certificates': False})
        assert r.status_code == 200
        body = auth_client.get(self.URL).get_json()['data']
        assert body['proxy_prune_replaced_certificates'] is False

    def test_patch_rejects_non_boolean(self, auth_client):
        r = auth_client.patch(self.URL, json={'proxy_prune_replaced_certificates': 'banana'})
        assert r.status_code == 400

    def test_get_defaults_to_false(self, app, auth_client):
        with app.app_context():
            from models import SystemConfig
            SystemConfig.query.filter_by(
                key='acme.proxy.prune_replaced_certificates').delete()
            db.session.commit()
        body = auth_client.get(self.URL).get_json()['data']
        assert body['proxy_prune_replaced_certificates'] is False
