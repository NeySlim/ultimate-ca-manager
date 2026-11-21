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


@pytest.fixture
def named_rows(app):
    from models import User
    from models.certificate_template import CertificateTemplate
    with app.app_context():
        made = [CertificateTemplate(name=n, template_type='server', description='',
                                     extensions_template='{}')
                for n in ('lk_tpl', 'lkXtpl')]
        made += [User(username=n, email=f'{n}@example.com', password_hash='x', role='viewer')
                 for n in ('lk_usr', 'lkXusr')]
        db.session.add_all(made)
        db.session.commit()
        keys = [(type(m), m.id) for m in made]
    yield
    with app.app_context():
        for model, rid in keys:
            model.query.filter_by(id=rid).delete()
        db.session.commit()


def test_template_search_underscore_is_literal(auth_client, named_rows):
    got = auth_client.get('/api/v2/templates?search=lk_tpl').get_json()['data']
    assert [t['name'] for t in got] == ['lk_tpl']


def test_user_search_underscore_is_literal(auth_client, named_rows):
    got = auth_client.get('/api/v2/users?search=lk_usr').get_json()['data']
    assert [u['username'] for u in got] == ['lk_usr']


@pytest.fixture
def audit_rows(app):
    from services.audit_service import AuditService
    with app.app_context():
        for name in ('lk_auditor', 'lkXauditor'):
            AuditService.log_action('lk_probe', username=name, details=f'{name} probe')


@pytest.mark.parametrize('param', ['search', 'username'])
def test_audit_search_underscore_is_literal(auth_client, audit_rows, param):
    got = auth_client.get(f'/api/v2/audit/logs?{param}=lk_auditor&per_page=100').get_json()['data']
    assert {e['username'] for e in got} == {'lk_auditor'}


def test_audit_search_percent_is_literal(auth_client, audit_rows):
    got = auth_client.get('/api/v2/audit/logs?search=lk%25auditor&per_page=100').get_json()['data']
    assert got == []
