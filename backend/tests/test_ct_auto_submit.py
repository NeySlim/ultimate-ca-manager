"""`ct_auto_submit` submits every newly issued certificate, on every path.

The switch was only honoured by the mTLS enrolment path; a certificate from
the issuance form, a CSR, a renewal, ACME or SCEP was never submitted. The
submission now sits in `apply_ct_policy`, which every issuance path calls,
and runs in the background once the issuance commits.
"""
import json
import threading
import uuid

import pytest
from cryptography import x509

from models import SystemConfig, db
import utils.ct_client as ct_client

KEYS = ('ct_enabled', 'ct_auto_submit', 'ct_embed_sct')


@pytest.fixture
def ct_settings(app):
    with app.app_context():
        saved = {k: getattr(SystemConfig.query.filter_by(key=k).first(), 'value', None) for k in KEYS}

    def apply(**values):
        with app.app_context():
            for k, v in values.items():
                row = SystemConfig.query.filter_by(key=k).first()
                if row is None:
                    row = SystemConfig(key=k)
                    db.session.add(row)
                row.value = 'true' if v else 'false'
            db.session.commit()

    yield apply
    with app.app_context():
        for k, v in saved.items():
            row = SystemConfig.query.filter_by(key=k).first()
            if v is None:
                if row:
                    db.session.delete(row)
            else:
                row.value = v
        db.session.commit()


@pytest.fixture
def submissions(monkeypatch):
    calls = []

    def fake_collect(chain, urls=None):
        calls.append(chain)
        return []

    monkeypatch.setattr(ct_client, 'collect_scts', fake_collect)
    monkeypatch.setattr(ct_client, 'collect_precert_scts', lambda chain, urls=None: [])
    return calls


def _cn():
    return f'ct-{uuid.uuid4().hex[:8]}.example.com'


def _drain():
    for thread in threading.enumerate():
        if thread.name == ct_client.AUTO_SUBMIT_THREAD:
            thread.join(timeout=20)


def test_the_issuance_form_submits_the_certificate(ct_settings, submissions, create_cert):
    ct_settings(ct_enabled=True, ct_auto_submit=True, ct_embed_sct=False)
    cn = _cn()
    create_cert(cn=cn)
    _drain()
    assert len(submissions) == 1
    leaf = x509.load_pem_x509_certificate(submissions[0][0].encode())
    assert cn in leaf.subject.rfc4514_string()
    assert len(submissions[0]) == 2  # leaf and issuer


def test_nothing_is_submitted_when_off(ct_settings, submissions, create_cert):
    ct_settings(ct_enabled=True, ct_auto_submit=False, ct_embed_sct=False)
    create_cert(cn=_cn())
    _drain()
    assert submissions == []


def test_nothing_is_submitted_when_ct_is_disabled(ct_settings, submissions, create_cert):
    ct_settings(ct_enabled=False, ct_auto_submit=True, ct_embed_sct=False)
    create_cert(cn=_cn())
    _drain()
    assert submissions == []


def test_embedding_takes_precedence(ct_settings, submissions, create_cert):
    ct_settings(ct_enabled=True, ct_auto_submit=True, ct_embed_sct=True)
    create_cert(cn=_cn())
    _drain()
    assert submissions == []


def test_the_issuance_does_not_wait_for_the_logs(app, ct_settings, monkeypatch, create_cert):
    ct_settings(ct_enabled=True, ct_auto_submit=True, ct_embed_sct=False)
    release = threading.Event()
    sct = {'log_id': 'test-log', 'timestamp': 1}

    def slow_collect(chain, urls=None):
        release.wait(20)
        return [sct]

    monkeypatch.setattr(ct_client, 'collect_scts', slow_collect)
    monkeypatch.setattr(ct_client, 'collect_precert_scts', lambda chain, urls=None: [])
    cert_id = create_cert(cn=_cn())['id']
    # Issued while the log has not answered yet
    assert any(t.name == ct_client.AUTO_SUBMIT_THREAD for t in threading.enumerate())
    release.set()
    _drain()
    with app.app_context():
        stored = SystemConfig.query.filter_by(key=f'cert_scts_{cert_id}').first()
        assert stored is not None and json.loads(stored.value) == [sct]
        db.session.delete(stored)
        db.session.commit()


def test_a_rolled_back_issuance_is_not_submitted(app, ct_settings, submissions, create_ca):
    from cryptography.hazmat.primitives import hashes
    from cryptography.hazmat.primitives.asymmetric import ec
    from datetime import datetime, timedelta, timezone
    ct_settings(ct_enabled=True, ct_auto_submit=True, ct_embed_sct=False)
    key = ec.generate_private_key(ec.SECP256R1())
    name = x509.Name([x509.NameAttribute(x509.NameOID.COMMON_NAME, _cn())])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name).public_key(key.public_key())
            .serial_number(x509.random_serial_number()).not_valid_before(now)
            .not_valid_after(now + timedelta(days=1)).sign(key, hashes.SHA256()))
    with app.app_context():
        ct_client.apply_ct_policy(cert, cert, key)
        db.session.rollback()
        db.session.commit()
    _drain()
    assert submissions == []
