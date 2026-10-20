"""A restored EAB credential keeps the domains it was limited to.

The restorer copied every column but `allowed_domains`, so a restricted
credential came back as NULL, which reads as "every domain".
"""
import base64

from models import db
from models.acme_models import AcmeEabCredential
from services.backup import manifest

PASSWORD = 'Correct-Horse-Battery-9'
LIMITED = ['example.org', '*.svc.example.org']
KIDS = ('restore-eab-limited', 'restore-eab-blocked', 'restore-eab-open')


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    return {name: name in names for name in manifest.SECTIONS}


def _credential(kid, allowed):
    cred = AcmeEabCredential(
        kid=kid,
        hmac_key_b64=base64.b64encode(f'{kid}-secret'.encode()).decode(),
        label=kid,
        status='active',
    )
    cred.allowed_domains = allowed
    db.session.add(cred)
    return cred


def _seed():
    _credential(KIDS[0], LIMITED)
    _credential(KIDS[1], [])
    _credential(KIDS[2], None)
    db.session.commit()


def _cleanup():
    AcmeEabCredential.query.filter(AcmeEabCredential.kid.in_(KIDS)).delete(
        synchronize_session=False)
    db.session.commit()


def _limits():
    return {c.kid: c.allowed_domains for c in
            AcmeEabCredential.query.filter(AcmeEabCredential.kid.in_(KIDS))}


EXPECTED = {KIDS[0]: LIMITED, KIDS[1]: [], KIDS[2]: None}


def test_a_restore_onto_an_empty_table_recreates_the_limits(app):
    with app.app_context():
        _cleanup()
        try:
            _seed()
            blob = _service().create_backup(
                PASSWORD, include=_only('acme_eab_credentials'))
            _cleanup()

            _service().restore_backup(blob, PASSWORD)
            db.session.expire_all()

            assert _limits() == EXPECTED
        finally:
            _cleanup()


def test_a_restore_over_existing_rows_puts_the_limits_back(app):
    with app.app_context():
        _cleanup()
        try:
            _seed()
            blob = _service().create_backup(
                PASSWORD, include=_only('acme_eab_credentials'))
            for cred in AcmeEabCredential.query.filter(
                    AcmeEabCredential.kid.in_(KIDS)):
                cred.allowed_domains = ['changed.example.net']
            db.session.commit()

            _service().restore_backup(blob, PASSWORD)
            db.session.expire_all()

            assert _limits() == EXPECTED
        finally:
            _cleanup()


def test_a_restore_refuses_limits_it_cannot_read(app):
    import pytest
    from services.backup.errors import BackupSchemaError
    from tests.test_backup_restore_failfast import PASSWORD as FF_PASSWORD, _forged

    with app.app_context():
        _cleanup()
        try:
            blob = _forged(['acme_eab_credentials'], acme_eab_credentials=[{
                'kid': KIDS[0],
                'hmac_key_b64': base64.b64encode(b'odd-limits').decode(),
                'status': 'active',
                'allowed_domains': 42,
            }])
            with pytest.raises(BackupSchemaError) as refusal:
                _service().restore_backup(blob, FF_PASSWORD)
            assert KIDS[0] in str(refusal.value)
            assert AcmeEabCredential.query.filter_by(kid=KIDS[0]).first() is None
        finally:
            _cleanup()
