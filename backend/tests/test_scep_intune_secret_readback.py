"""The Intune client secret reads back whether or not it was stored encrypted.

`decrypt_value` answers None for anything that is not one of its own tokens,
and an `or ''` turned that into an empty string. Two values land in that
column without being encrypted: one written before at-rest encryption was
enabled, and one put back by a restore -- an archive carries secrets in the
clear on purpose, so they survive a change of database key. Both read back as
no secret at all, and the Intune enrolment stopped working without a word.
Since 092 the column belongs to the app registration the profiles share.
"""
import pytest

from models import db
from models.scep import IntuneApp, ScepProfile
from utils.encryption import encrypt_value

SECRET = 'zz-intune-client-secret'


@pytest.fixture
def bound(app, create_ca):
    """An app registration and a profile bound to it, removed afterwards."""
    ca_refid = create_ca(cn='Intune readback CA')['refid']  # PostgreSQL enforces ca_refid
    with app.app_context():
        registration = IntuneApp(name='zz-intune-readback', tenant_id='zz-tenant',
                                 client_id='zz-client', client_secret='x')
        db.session.add(registration)
        db.session.flush()
        row = ScepProfile(name='zz-intune-readback', url_slug='zz-intune-readback',
                          ca_refid=ca_refid, intune_app_id=registration.id)
        db.session.add(row)
        db.session.commit()
        ids = (registration.id, row.id)

    yield ids

    with app.app_context():
        ScepProfile.query.filter_by(name='zz-intune-readback').delete(
            synchronize_session=False)
        IntuneApp.query.filter_by(name='zz-intune-readback').delete(
            synchronize_session=False)
        db.session.commit()


def _store(app_id, value):
    registration = db.session.get(IntuneApp, app_id)
    registration.client_secret = value
    db.session.commit()
    return registration


class TestTheSecretComesBack:
    def test_an_encrypted_secret_is_decrypted(self, app, bound):
        with app.app_context():
            registration = _store(bound[0], encrypt_value(SECRET))
            assert registration.decrypted_secret() == SECRET

    def test_a_secret_a_restore_put_back_in_the_clear_still_reads(self, app, bound):
        """What the restore writes: the archive carries it readable so that it
        survives an installation with another database key."""
        with app.app_context():
            registration = _store(bound[0], SECRET)
            assert registration.decrypted_secret() == SECRET, \
                'the secret read back as nothing at all'

    def test_the_profile_reads_the_secret_of_its_app(self, app, bound):
        with app.app_context():
            _store(bound[0], encrypt_value(SECRET))
            profile = db.session.get(ScepProfile, bound[1])
            assert profile.intune_credentials() == ('zz-tenant', 'zz-client', SECRET)
            assert profile.decrypted_intune_secret() == SECRET

    def test_no_app_is_no_secret(self, app, bound):
        with app.app_context():
            profile = db.session.get(ScepProfile, bound[1])
            profile.intune_app_id = None
            db.session.commit()
            assert profile.intune_credentials() == ('', '', '')
