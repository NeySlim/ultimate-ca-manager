"""Which authority a locally served ACME zone may be bound to.

The two mapping tables answer the same question and answered it differently.
`acme_domains` asks `signing_ca_problem`, which names six reasons an authority
cannot sign; `acme_local_domains` checked two of them, so a zone could be
bound to an authority that is revoked, that sits under a revoked one, or that
has been taken offline.

Nothing is signed by such an authority: `_check_ca_offline` raises before any
key is used. What happens instead is that the operator saves a mapping
issuance will refuse, nothing says so, and the client retries an order that
never completes, because that refusal is not a terminal failure.

The interface already filters the picker (`lib/caSelection.js`), so the gap is
reachable through the API alone.
"""
import pytest

from models import db


def _zone(name):
    return f'{name}.signing-ca.test'


@pytest.fixture
def usable_ca(app, create_ca):
    return create_ca(cn='Local Domain Usable CA')


@pytest.fixture
def offline_ca(app, create_ca):
    """An authority that could sign and has been taken out of service."""
    from models import CA

    ca = create_ca(cn='Local Domain Offline CA')
    with app.app_context():
        row = db.session.get(CA, ca['id'])
        row.offline = True
        db.session.commit()
    return ca


@pytest.fixture(autouse=True)
def _clean(app):
    yield
    with app.app_context():
        from models.acme_models import AcmeLocalDomain
        AcmeLocalDomain.query.filter(
            AcmeLocalDomain.domain.like('%.signing-ca.test')).delete(
                synchronize_session=False)
        db.session.commit()


def _create(client, domain, ca_id):
    return client.post('/api/v2/acme/local-domains',
                       json={'domain': domain, 'issuing_ca_id': ca_id})


@pytest.fixture
def revoked_ca(app, create_ca):
    from models import CA

    ca = create_ca(cn='Local Domain Revoked CA')
    with app.app_context():
        db.session.get(CA, ca['id']).revoked = True
        db.session.commit()
    return ca


class TestAZoneIsNotBoundToAnAuthorityThatCannotSign:
    def test_an_offline_authority_is_refused(self, auth_client, offline_ca):
        response = _create(auth_client, _zone('offline'), offline_ca['id'])

        assert response.status_code == 400, response.data
        assert b'offline' in response.data.lower(), (
            'the refusal must name the reason, as the DNS-mapped table does')

    def test_a_revoked_authority_is_refused(self, auth_client, revoked_ca):
        response = _create(auth_client, _zone('revoked'), revoked_ca['id'])

        assert response.status_code == 400, response.data
        assert b'revoked' in response.data.lower()

    def test_every_reason_the_rule_names_is_refused(self, app, auth_client,
                                                    usable_ca, monkeypatch):
        """The route must ask the shared rule, not a list of its own.

        Testing each of the six causes end to end would mostly re-test the
        rule, which has its own coverage. What belongs here is that the route
        delegates: whatever reason the rule gives, the route refuses and
        repeats it. A route that kept its own two checks passes the two cases
        above by accident and fails this one.
        """
        import api.v2.acme_local_domains as route

        monkeypatch.setattr(route, 'signing_ca_problem',
                            lambda ca: 'a reason only the rule knows')

        response = _create(auth_client, _zone('delegates'), usable_ca['id'])

        assert response.status_code == 400, response.data
        assert b'a reason only the rule knows' in response.data

    def test_a_usable_authority_is_accepted(self, auth_client, usable_ca):
        response = _create(auth_client, _zone('usable'), usable_ca['id'])
        assert response.status_code == 201, response.data


class TestAZoneAlreadyBoundStaysEditable:
    """The clause the DNS-mapped table already carries.

    An authority can be taken offline after a zone was bound to it. Re-judging
    it on every change would leave that zone frozen: the operator could no
    longer correct it, nor turn its automatic approval off.
    """

    @pytest.fixture
    def bound_then_offline(self, app, auth_client, usable_ca):
        from models import CA
        from models.acme_models import AcmeLocalDomain

        assert _create(auth_client, _zone('bound'),
                       usable_ca['id']).status_code == 201
        with app.app_context():
            db.session.get(CA, usable_ca['id']).offline = True
            db.session.commit()
            zone = AcmeLocalDomain.query.filter_by(
                domain=_zone('bound')).one()
            return zone.id, usable_ca['id']

    def test_another_field_can_still_be_changed(self, auth_client,
                                                bound_then_offline):
        zone_id, _ca_id = bound_then_offline
        response = auth_client.put(f'/api/v2/acme/local-domains/{zone_id}',
                                   json={'auto_approve': True})
        assert response.status_code == 200, response.data

    def test_the_whole_object_can_be_sent_back(self, auth_client,
                                               bound_then_offline):
        """What a form does: it returns every field, the authority included."""
        zone_id, ca_id = bound_then_offline
        response = auth_client.put(
            f'/api/v2/acme/local-domains/{zone_id}',
            json={'issuing_ca_id': ca_id, 'auto_approve': True})
        assert response.status_code == 200, response.data

    def test_the_identifier_may_come_back_as_text(self, auth_client,
                                                  bound_then_offline):
        """The column is an integer and JSON may carry the identifier as a
        string. Compared without normalising, the two differ, the authority is
        re-judged although it did not change, and the zone is frozen after
        all. This is the case a bare `!=` would fail."""
        zone_id, ca_id = bound_then_offline
        response = auth_client.put(
            f'/api/v2/acme/local-domains/{zone_id}',
            json={'issuing_ca_id': str(ca_id), 'auto_approve': False})
        assert response.status_code == 200, response.data

    def test_moving_to_an_unusable_authority_is_still_refused(
            self, auth_client, bound_then_offline, offline_ca):
        zone_id, _ca_id = bound_then_offline
        response = auth_client.put(
            f'/api/v2/acme/local-domains/{zone_id}',
            json={'issuing_ca_id': offline_ca['id']})
        assert response.status_code == 400, response.data
        assert b'offline' in response.data.lower()
