"""An auto-approved authorization claims no validation method (RFC 8657 §4).

No challenge was performed, so none is listed as valid (RFC 8555 §7.1.4), and
a CAA `validationmethods` parameter then cannot authorize the issuance.
"""
import pytest

from models import db

pytestmark = pytest.mark.usefixtures('drop_new_cas_and_certificates')


def test_auto_approved_authorizations_name_no_validation_method(app, monkeypatch, caplog):
    import logging

    from models.acme_models import AcmeAccount
    from services.acme.acme_service import AcmeService

    with app.app_context():
        account = AcmeAccount.query.filter_by(account_id='acct-caa-auto-approved').first()
        if account is None:
            account = AcmeAccount(account_id='acct-caa-auto-approved', jwk='{}',
                                  jwk_thumbprint='caa-auto-approved', status='valid', contact='[]')
            db.session.add(account)
            db.session.commit()
        service = AcmeService(base_url='http://localhost')
        monkeypatch.setattr(type(service), '_is_domain_auto_approved',
                            lambda self, domain: True, raising=False)
        order = service.create_order(account.account_id, [
            {'type': 'dns', 'value': 'www.caa-auto.example'},
            {'type': 'dns', 'value': '*.caa-auto.example'},
        ])
        authorizations = list(order.authorizations)
        assert authorizations and all(a.status == 'valid' for a in authorizations)
        assert [c.type for a in authorizations for c in a.challenges if c.status == 'valid'] == []

        with caplog.at_level(logging.DEBUG, logger='services.acme.mixins.issuance'):
            _, methods = service._caa_request_context(order)
        assert methods == {'www.caa-auto.example': None, '*.caa-auto.example': None}
        # Expected on every auto-approved finalization: informational, not a warning
        noted = [r for r in caplog.records if 'No validated ACME challenge' in r.getMessage()]
        assert noted and all(r.levelno == logging.INFO for r in noted)


def test_auto_approved_pre_authorization_reused_by_an_order_names_no_method(app, monkeypatch):
    # newAuthz (RFC 8555 §7.4.1) must not create a valid challenge either:
    # an order reusing it would otherwise claim dns-01 for a wildcard.
    from models.acme_models import AcmeAccount
    from services.acme.acme_service import AcmeService

    with app.app_context():
        account = AcmeAccount.query.filter_by(account_id='acct-caa-auto-preauth').first()
        if account is None:
            account = AcmeAccount(account_id='acct-caa-auto-preauth', jwk='{}',
                                  jwk_thumbprint='caa-auto-preauth', status='valid', contact='[]')
            db.session.add(account)
            db.session.commit()
        service = AcmeService(base_url='http://localhost')
        monkeypatch.setattr(type(service), '_is_domain_auto_approved',
                            lambda self, domain: True, raising=False)
        pre = service.create_pre_authorization(
            account.account_id, {'type': 'dns', 'value': '*.caa-preauth.example'})
        assert pre.status == 'valid'
        assert [c.type for c in pre.challenges] == []

        order = service.create_order(account.account_id, [
            {'type': 'dns', 'value': '*.caa-preauth.example'},
        ])
        _, methods = service._caa_request_context(order)
        assert methods == {'*.caa-preauth.example': None}
