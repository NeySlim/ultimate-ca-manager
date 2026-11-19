"""A `_` or `%` typed in a search box matches itself, on both engines."""
import pytest

from models import Group, db
from models.truststore import TrustedCertificate

pytestmark = pytest.mark.usefixtures('drop_new_users')


@pytest.fixture
def rows(app):
    with app.app_context():
        group = Group(name='lk_group', description='')
        other = Group(name='lkXgroup', description='')
        trusted = TrustedCertificate(
            name='lk_trusted', certificate_pem='x', fingerprint_sha256='ab' * 32,
            subject='CN=lk_trusted', purpose='custom')
        decoy = TrustedCertificate(
            name='lkXtrusted', certificate_pem='x', fingerprint_sha256='cd' * 32,
            subject='CN=lkXtrusted', purpose='custom')
        db.session.add_all([group, other, trusted, decoy])
        db.session.commit()
        made = ([group, other], [trusted, decoy])
        ids = ([g.id for g in made[0]], [t.id for t in made[1]])
    yield
    with app.app_context():
        Group.query.filter(Group.id.in_(ids[0])).delete(synchronize_session=False)
        TrustedCertificate.query.filter(TrustedCertificate.id.in_(ids[1])).delete(
            synchronize_session=False)
        db.session.commit()


def test_group_search_underscore_is_literal(auth_client, rows):
    got = auth_client.get('/api/v2/groups?search=lk_group').get_json()['data']
    assert [g['name'] for g in got] == ['lk_group']


def test_truststore_search_underscore_is_literal(auth_client, rows):
    got = auth_client.get('/api/v2/truststore?search=lk_trusted').get_json()['data']
    assert [t['name'] for t in got] == ['lk_trusted']
