"""The SSH CA list answers every authority unless a page is asked for, as the CA list does."""
import uuid

import pytest

from models import db
from models.ssh import SSHCertificateAuthority


@pytest.fixture
def many_cas(app):
    tag = uuid.uuid4().hex[:8]
    ids = []
    with app.app_context():
        for i in range(23):
            ca = SSHCertificateAuthority(
                refid=str(uuid.uuid4()), descr=f'listall-{tag}-{i:02d}', ca_type='user',
                public_key='ssh-ed25519 AAAA', private_key='x', key_type='ed25519',
                fingerprint=f'SHA256:{tag}{i}')
            db.session.add(ca)
            db.session.flush()
            ids.append(ca.id)
        db.session.commit()
    yield tag
    with app.app_context():
        SSHCertificateAuthority.query.filter(
            SSHCertificateAuthority.id.in_(ids)).delete(synchronize_session=False)
        db.session.commit()


def test_no_page_asked_returns_every_authority(auth_client, many_cas):
    r = auth_client.get(f'/api/v2/ssh/cas?search=listall-{many_cas}')
    body = r.get_json()
    assert r.status_code == 200
    assert len(body['data']) == 23
    assert body['meta']['total'] == 23


def test_a_page_asked_is_still_a_page(auth_client, many_cas):
    r = auth_client.get(f'/api/v2/ssh/cas?search=listall-{many_cas}&per_page=10&page=3')
    body = r.get_json()
    assert len(body['data']) == 3
    assert body['meta']['total'] == 23 and body['meta']['total_pages'] == 3
