"""The compliance score in SQL equals calculate_compliance_score row by row, and the two
compliance routes report the same population (the active certificates) with the same counts."""
import uuid
from datetime import timedelta

import pytest
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, ed25519, rsa
from sqlalchemy import select

from models import Certificate, db
from services import compliance_sql
from services.compliance_service import calculate_compliance_score
from tests.conftest import get_json
from tests.dashboard_pem import self_signed, sha1_rsa
from utils.datetime_utils import utc_now

DASHBOARD = '/api/v2/dashboard/compliance'
CERTIFICATES = '/api/v2/certificates/compliance'
GRADES = ('A+', 'A', 'B', 'C', 'D', 'F')
POPULATION = {'definition': 'active', 'criteria': ['issued', 'not_revoked', 'not_archived', 'not_expired'],
              'filter_hint': {'live': 'true'}}


def _rsa(bits, algorithm=hashes.SHA256()):
    return self_signed(rsa.generate_private_key(public_exponent=65537, key_size=bits), algorithm)


@pytest.fixture(scope='module')
def pems():
    return {
        'rsa1024': _rsa(1024), 'rsa2048': _rsa(2048), 'rsa3072': _rsa(3072, hashes.SHA384()),
        'rsa4096': _rsa(4096, hashes.SHA512()), 'rsa_sha224': _rsa(2048, hashes.SHA224()), 'sha1': sha1_rsa(),
        'p256': self_signed(ec.generate_private_key(ec.SECP256R1())),
        'p384': self_signed(ec.generate_private_key(ec.SECP384R1()), hashes.SHA384()),
        'p521': self_signed(ec.generate_private_key(ec.SECP521R1()), hashes.SHA512()),
        'k256': self_signed(ec.generate_private_key(ec.SECP256K1())),
        'ed25519': self_signed(ed25519.Ed25519PrivateKey.generate()),
    }


@pytest.fixture
def rows(app):
    created = []

    def add(pem, lifetime_days=90, left_days=None, **kw):
        now = utc_now()
        kw.setdefault('prv', 'key')
        left = lifetime_days - 1 if left_days is None else left_days
        row = Certificate(refid=str(uuid.uuid4()), descr='compliance-score-test', crt=pem,
                          valid_from=now + timedelta(days=left - lifetime_days),
                          valid_to=now + timedelta(days=left), **kw)
        db.session.add(row)
        db.session.flush()
        created.append(row.id)
        return row
    yield add
    with app.app_context():
        Certificate.query.filter(Certificate.id.in_(created)).delete(synchronize_session=False)
        db.session.commit()


def _sql_scores(ids):
    now = utc_now()
    dialect = db.session.get_bind().dialect.name
    return dict(db.session.execute(select(Certificate.id, compliance_sql.score_expression(dialect, now))
                                   .where(Certificate.id.in_(ids))).all())


def test_the_sql_score_is_the_python_score(app, pems, rows):
    with app.app_context():
        made = [rows(pem) for pem in pems.values()]
        made += [
            rows(pems['p256'], lifetime_days=398, cert_type='server_cert'),
            rows(pems['p256'], lifetime_days=400, cert_type='server_cert'),
            rows(pems['p256'], lifetime_days=825),
            rows(pems['p256'], lifetime_days=827),
            rows(pems['rsa2048'], lifetime_days=3650, cert_type='ca'),
            rows(pems['rsa2048'], lifetime_days=3650, cert_type='Intermediate'),
            rows(pems['p384'], left_days=3), rows(pems['p384'], left_days=20), rows(pems['p384'], left_days=200),
            rows(pems['p256'], san_dns='["a.example"]'), rows(pems['p256'], san_dns='[]'),
            rows(pems['p256'], san_ip='["10.0.0.1"]', san_dns=''), rows(pems['p256'], san_uri='["urn:x"]'),
            rows(pems['p256'], san_email='null'),
            rows(pems['rsa4096'], revoked=True), rows(pems['rsa4096'], left_days=-2),
            rows(pems['p384'], san_dns='["top.example"]'),                      # A+
            rows(pems['k256'], left_days=3, lifetime_days=500),                 # D
            rows(pems['rsa1024'], revoked=True, lifetime_days=900),             # F
        ]
        no_dates = rows(pems['ed25519'])
        no_dates.valid_from = no_dates.valid_to = None
        made.append(no_dates)
        db.session.flush()
        expected = {r.id: calculate_compliance_score(r.to_dict())['score'] for r in made}
        assert _sql_scores(list(expected)) == expected
        # every grade is reached, so a wrong threshold or part shows
        assert {compliance_sql.grade_of(s) for s in expected.values()} == set(GRADES)
        db.session.rollback()


def _get(client, url):
    r = client.get(url)
    assert r.status_code == 200, r.data
    return get_json(r)['data']


def test_both_routes_report_the_same_population_and_counts(auth_client):
    dashboard, certificates = _get(auth_client, DASHBOARD), _get(auth_client, CERTIFICATES)
    count = dashboard['population']['count']
    assert dashboard['population'] == certificates['population'] == {**POPULATION, 'count': count}
    assert dashboard['total'] == certificates['total'] == count
    assert dashboard['score']['distribution'] == certificates['distribution']
    assert dashboard['score']['average'] == certificates['average_score']
    assert sum(certificates['distribution'].values()) == count
    assert set(certificates['distribution']) == set(GRADES)


def test_counts_cover_the_active_certificates_only(app, auth_client, pems, rows):
    before_d, before_c = _get(auth_client, DASHBOARD), _get(auth_client, CERTIFICATES)
    with app.app_context():
        good = rows(pems['p384'], san_dns='["ok.example"]')            # A+, no deviation
        weak = rows(pems['rsa2048'], san_dns='["weak.example"]')       # rsa_below_3072
        keyless = rows(pems['p256'], prv=None, san_dns='["c.example"]')  # no_private_key
        # Neither expired, revoked nor archived certificates belong to the population
        rows(pems['p384'], left_days=-1)
        rows(pems['p384'], revoked=True)
        rows(pems['p384'], archived=True)
        expected = [calculate_compliance_score(r.to_dict())['grade'] for r in (good, weak, keyless)]
        db.session.commit()
    after_d, after_c = _get(auth_client, DASHBOARD), _get(auth_client, CERTIFICATES)
    assert after_c['total'] - before_c['total'] == 3
    assert after_d['population']['count'] - before_d['population']['count'] == 3
    assert after_d['compliant'] - before_d['compliant'] == 1
    delta = {g: after_c['distribution'][g] - before_c['distribution'][g] for g in GRADES}
    assert delta == {g: expected.count(g) for g in GRADES}
    assert after_d['score']['distribution'] == after_c['distribution']


def test_the_grade_follows_the_average(auth_client):
    data = _get(auth_client, DASHBOARD)
    if data['population']['count']:
        assert data['score']['grade'] == compliance_sql.grade_of(data['score']['average'])
    else:
        assert data['score']['grade'] is None


@pytest.mark.parametrize('url', [DASHBOARD, CERTIFICATES])
def test_requires_auth(client, url):
    assert client.get(url).status_code == 401
