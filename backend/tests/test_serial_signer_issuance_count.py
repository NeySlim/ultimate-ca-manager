"""Renewal in place and the certificates UCM signs for its own services count in
the CA's issuance counter, in the transaction that writes the certificate."""
import json

import pytest

from models import Certificate, db
from tests.seeded_rows import _remove_what_the_test_created  # noqa: F401 (autouse)
from tests.seeded_rows import issuance_count as _count


def _issue(auth_client, ca_id, cn):
    r = auth_client.post('/api/v2/certificates', data=json.dumps(
        {'cn': cn, 'ca_id': ca_id, 'validity_days': 30}), content_type='application/json')
    assert r.status_code in (200, 201), r.data
    return json.loads(r.data)['data']['id']


def test_renewal_in_place_counts_the_renewed_certificate(app, auth_client, create_ca):
    ca = create_ca(cn='Renewal count CA')
    cert_id = _issue(auth_client, ca['id'], 'renew-count.example.test')
    assert _count(app, ca['id']) == (1, 1)
    r = auth_client.post(f'/api/v2/certificates/{cert_id}/renew', data='{}',
                         content_type='application/json')
    assert r.status_code == 200, r.data
    assert _count(app, ca['id']) == (2, 1)


def test_a_renewal_whose_commit_fails_counts_nothing(app, auth_client, create_ca, monkeypatch):
    from services.cert import renewal
    ca = create_ca(cn='Failed renewal count CA')
    cert_id = _issue(auth_client, ca['id'], 'renew-fail-count.example.test')

    def refused(*_args):
        db.session.rollback()
        return False
    monkeypatch.setattr(renewal, 'commit_or_rollback', refused)
    with app.app_context():
        with pytest.raises(renewal.RenewalError):
            renewal.renew_certificate_in_place(db.session.get(Certificate, cert_id))
    assert _count(app, ca['id']) == (1, 1)


def test_a_tsa_signer_counts_its_certificate(app, create_ca):
    from models import CA
    from services.tsa_signer_cert import issue_tsa_signer_certificate
    ca = create_ca(cn='TSA signer count CA')
    with app.app_context():
        issue_tsa_signer_certificate(ca=db.session.get(CA, ca['id']), cn='tsa-count.example.test')
    assert _count(app, ca['id']) == (1, 1)


def test_a_tsa_signer_whose_commit_fails_counts_nothing(app, create_ca, monkeypatch):
    from models import CA
    from services import tsa_signer_cert

    def refused(*_args):
        db.session.rollback()
        return False, None
    monkeypatch.setattr(tsa_signer_cert, 'safe_commit', refused)
    ca = create_ca(cn='Failed TSA signer count CA')
    with app.app_context():
        with pytest.raises(tsa_signer_cert.TsaSignerIssueError):
            tsa_signer_cert.issue_tsa_signer_certificate(ca=db.session.get(CA, ca['id']))
    assert _count(app, ca['id']) == (0, 0)
