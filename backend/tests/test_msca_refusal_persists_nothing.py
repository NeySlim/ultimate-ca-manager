"""A refused connection update keeps nothing it was asked to change.

The fields of a Microsoft CA connection are applied to the row one at a time
with no commit between them. An error part way down (simulated below, a value
of the wrong type being a 400 before any field is applied) answers 500 with the
earlier fields still staged.

That was harmless until the refusal was audited, because nothing committed.
`AuditService.log_action` commits the session it is given, so the audit entry
for the refusal was what made the refused change durable: a request naming a
new server, a new user and a new password, with one field the route cannot
read, was answered "Failed to update connection" and kept the rest.
"""
import json

import pytest

from models import db
from models.msca import MicrosoftCA


@pytest.fixture
def a_connection(app, request):
    # The suite shares one database and `name` is unique, so each test gets
    # its own row rather than the fixture colliding with itself.
    label = f'msca-refusal-probe-{request.node.name[:40]}'
    with app.app_context():
        row = MicrosoftCA(
            name=label,
            server='ca.internal.example',
            ca_name='Example Issuing CA',
            auth_method='basic',
            username='service-account',
        )
        db.session.add(row)
        db.session.commit()
        return row.id, label


@pytest.fixture
def fails_part_way(monkeypatch):
    """The CRL URL is read after the name and server are applied: make it raise there."""
    import api.v2.msca as routes

    def boom(raw):
        raise RuntimeError('unreadable field')

    monkeypatch.setattr(routes, '_clean_crl_url', boom)
    return {'name': 'renamed-by-a-refused-request', 'crl_url': 'http://crl.example/ca.crl'}


class TestARefusedUpdateChangesNothing:
    def test_a_field_of_the_wrong_type_keeps_the_fields_before_it(
            self, app, auth_client, a_connection, fails_part_way):
        connection_id, label = a_connection
        r = auth_client.put(
            f'/api/v2/microsoft-cas/{connection_id}',
            data=json.dumps({**fails_part_way, 'server': 'other.internal.example'}),
            content_type='application/json')
        assert r.status_code == 500, (
            f'this request is supposed to be refused: {r.status_code}')

        with app.app_context():
            row = db.session.get(MicrosoftCA, connection_id)
            assert row.name == label, (
                'the refused request renamed the connection anyway: '
                f'{row.name!r}')
            assert row.server == 'ca.internal.example', (
                f'the refused request changed the server: {row.server!r}')

    def test_the_refusal_is_still_recorded(
            self, app, auth_client, a_connection, fails_part_way):
        connection_id, label = a_connection
        """Rolling back must not cost the trail: a refused attempt on a
        connection that holds credentials is worth knowing about."""
        from models import AuditLog

        auth_client.put(
            f'/api/v2/microsoft-cas/{connection_id}',
            data=json.dumps(fails_part_way),
            content_type='application/json')

        with app.app_context():
            entries = AuditLog.query.filter_by(
                action='msca.update', success=False).all()
            assert entries, 'the refusal left no trace at all'
