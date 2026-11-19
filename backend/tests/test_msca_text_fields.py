"""A null or non-text value of a Microsoft CA connection field is a 400 naming the field, not a 500."""
import json
import uuid

import pytest

from models import db
from models.msca import MicrosoftCA
from tests.conftest import get_json

BASE = '/api/v2/microsoft-cas'


def _send(client, method, url, body):
    return getattr(client, method)(url, data=json.dumps(body), content_type='application/json')


@pytest.fixture
def kerberos_id(app):
    with app.app_context():
        row = MicrosoftCA(name=f'krb-text-{uuid.uuid4().hex[:8]}', server='adcs.corp.local',
                          auth_method='kerberos', kerberos_principal='svc@CORP.LOCAL', enabled=True)
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    yield row_id
    with app.app_context():
        MicrosoftCA.query.filter_by(id=row_id).delete()
        db.session.commit()


@pytest.mark.parametrize('field', ['name', 'server', 'ca_name', 'ca_bundle', 'default_template',
                                   'kerberos_principal', 'kerberos_keytab_path'])
@pytest.mark.parametrize('value', [None, 5], ids=['null', 'number'])
def test_a_non_text_value_is_refused_on_update(app, auth_client, kerberos_id, field, value):
    r = _send(auth_client, 'put', f'{BASE}/{kerberos_id}', {field: value})
    assert r.status_code == 400, r.data
    assert field in get_json(r)['message']


@pytest.mark.parametrize('field', ['name', 'server', 'ca_name', 'ca_bundle', 'default_template',
                                   'username', 'client_cert_pem'])
def test_a_non_text_value_is_refused_on_create(app, auth_client, field):
    body = {'name': f'krb-null-{uuid.uuid4().hex[:8]}', 'server': 'adcs.corp.local', 'auth_method': 'basic',
            field: None}
    r = _send(auth_client, 'post', BASE, body)
    assert r.status_code == 400, r.data
    assert field in get_json(r)['message']
