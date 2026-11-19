"""The trust store export keeps to the purposes asked for, one or several."""
import uuid

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import serialization

from models import db
from models.truststore import TrustedCertificate
from tests.test_export_unreadable_rows import _pem


@pytest.fixture
def entries(app):
    tag = uuid.uuid4().hex[:8]
    ids = []
    with app.app_context():
        for i, purpose in enumerate(['root_ca', 'intermediate_ca', 'custom']):
            row = TrustedCertificate(
                name=f'tp-{tag}-{purpose}', certificate_pem=_pem(f'tp-{tag}-{i}').decode(),
                fingerprint_sha256=uuid.uuid4().hex * 2, purpose=purpose)
            db.session.add(row)
            db.session.flush()
            ids.append(row.id)
        db.session.commit()
    yield tag
    with app.app_context():
        TrustedCertificate.query.filter(TrustedCertificate.id.in_(ids)).delete(
            synchronize_session=False)
        db.session.commit()


def _names(response):
    assert response.status_code == 200, response.data
    return [line[2:] for line in response.get_data(as_text=True).splitlines()
            if line.startswith('# tp-')]


def test_one_purpose(auth_client, entries):
    assert _names(auth_client.get('/api/v2/truststore/export?purpose=custom')) == [
        f'tp-{entries}-custom']


def test_several_purposes(auth_client, entries):
    got = _names(auth_client.get(
        '/api/v2/truststore/export?purpose=custom&purpose=root_ca'))
    assert got == [f'tp-{entries}-custom', f'tp-{entries}-root_ca']


def test_all_keeps_everything(auth_client, entries):
    assert len(_names(auth_client.get('/api/v2/truststore/export?purpose=all'))) >= 3


@pytest.fixture
def by_expiry(app):
    """One entry expired, one expiring within 90 days, one valid, one with no expiry."""
    from datetime import timedelta
    from utils.datetime_utils import utc_now
    tag = uuid.uuid4().hex[:8]
    ids = []
    now = utc_now()
    with app.app_context():
        for i, (label, until) in enumerate([
                ('expired', now - timedelta(days=5)), ('expiring', now + timedelta(days=30)),
                ('valid', now + timedelta(days=400)), ('open', None)]):
            row = TrustedCertificate(
                name=f'te-{tag}-{label}', certificate_pem=_pem(f'te-{tag}-{i}').decode(),
                fingerprint_sha256=uuid.uuid4().hex * 2, purpose='custom', not_after=until)
            db.session.add(row)
            db.session.flush()
            ids.append(row.id)
        db.session.commit()
    yield tag
    with app.app_context():
        TrustedCertificate.query.filter(TrustedCertificate.id.in_(ids)).delete(
            synchronize_session=False)
        db.session.commit()


def _expiry_names(response, tag):
    assert response.status_code == 200, response.data
    return sorted(line[2:].split('-', 2)[2] for line in response.get_data(as_text=True).splitlines()
                  if line.startswith(f'# te-{tag}'))


def test_the_expiry_filter_keeps_the_entries_in_that_state(auth_client, by_expiry):
    base = '/api/v2/truststore/export?purpose=custom'
    assert _expiry_names(auth_client.get(f'{base}&expiry=expired'), by_expiry) == ['expired']
    assert _expiry_names(auth_client.get(f'{base}&expiry=expiring&expiry=valid'), by_expiry) == [
        'expiring', 'open', 'valid']


def test_without_an_expiry_filter_everything_is_kept(auth_client, by_expiry):
    assert len(_expiry_names(auth_client.get('/api/v2/truststore/export?purpose=custom'),
                             by_expiry)) == 4


def test_an_unknown_expiry_value_is_refused(auth_client, by_expiry):
    assert auth_client.get('/api/v2/truststore/export?expiry=soon').status_code == 400
