"""References that could not be resolved on the first pass.

Sections are applied in an order that cannot satisfy every reference at once:
a certificate authority is restored before the HSM key it signs with, so the
first pass has nothing to resolve the link against. Rather than order the
sections by hand and hope, references are resolved again once every row
exists — these tests pin that they end up pointing at the right rows, and at
rows whose ids are deliberately not the ones the source used.
"""
import json

import pytest

from models import db
from services.backup import manifest


PASSWORD = 'Correct-Horse-Battery-9'


def _service():
    from services.backup_service import BackupService
    return BackupService()


def _only(*names):
    return {name: name in names for name in manifest.SECTIONS}


class TestHsmLinkSurvivesNewIds:
    def test_an_authority_finds_its_key_again(self, app, create_ca):
        from models import CA
        from models.hsm import HsmKey, HsmProvider

        authority = create_ca(cn='HSM Relink CA')
        with app.app_context():
            provider = HsmProvider(name='relink-provider', type='openbao')
            provider.config = json.dumps({'url': 'http://bao.test',
                                          'token': 'relink-token'})
            db.session.add(provider)
            db.session.commit()

            key = HsmKey(provider_id=provider.id, key_identifier='relink-key',
                         label='relink', algorithm='rsa', key_type='rsa',
                         purpose='sign')
            db.session.add(key)
            db.session.commit()

            ca = CA.query.filter_by(refid=authority['refid']).first()
            ca.hsm_key_id = key.id
            db.session.commit()
            key_id_before = key.id

            blob = _service().create_backup(
                PASSWORD,
                include=_only('certificate_authorities', 'hsm_keys', 'hsm_providers'))

            # The target loses the link and the key, and the key that comes
            # back will not get the id it had on the source.
            ca.hsm_key_id = None
            db.session.commit()
            db.session.delete(key)
            db.session.commit()
            filler = HsmKey(provider_id=provider.id, key_identifier='relink-filler',
                            label='filler', algorithm='rsa', key_type='rsa',
                            purpose='sign')
            db.session.add(filler)
            db.session.commit()

            try:
                _service().restore_backup(blob, PASSWORD)
                db.session.expire_all()

                restored_key = HsmKey.query.filter_by(
                    key_identifier='relink-key').first()
                assert restored_key is not None, 'the HSM key was not restored'
                assert restored_key.id != key_id_before, \
                    'the test needs the key to come back under a different id'

                ca = CA.query.filter_by(refid=authority['refid']).first()
                assert ca.hsm_key_id == restored_key.id, \
                    'the authority lost its HSM key, or points at another one'

                provider_back = HsmProvider.query.filter_by(
                    name='relink-provider').first()
                assert provider_back.get_config().get('token') == 'relink-token', \
                    'the provider credentials did not survive the restore'
            finally:
                ca = CA.query.filter_by(refid=authority['refid']).first()
                if ca:
                    ca.hsm_key_id = None
                db.session.commit()
                HsmKey.query.filter(HsmKey.key_identifier.in_(
                    ['relink-key', 'relink-filler'])).delete(synchronize_session=False)
                HsmProvider.query.filter_by(name='relink-provider').delete()
                db.session.commit()
