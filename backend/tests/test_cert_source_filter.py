"""
Certificate list ?source= filter (multi-select).

Certs carry a `source` column (manual/import/acme/letsencrypt/scep/est/msca).
The list endpoint filters on it, with legacy NULL treated as 'manual'.
"""
import base64
import json

from tests.conftest import get_json

BASE = '/api/v2/certificates'


def _seed(app, entries):
    """Insert minimal cert rows with given (cn, source). Returns list of ids."""
    import uuid
    from datetime import timedelta
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    from utils.datetime_utils import utc_now

    ids = []
    with app.app_context():
        from models import Certificate, db
        now = utc_now()
        for cn, source in entries:
            key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
            cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
                    .public_key(key.public_key()).serial_number(x509.random_serial_number())
                    .not_valid_before(now - timedelta(hours=1))
                    .not_valid_after(now + timedelta(days=365))
                    .sign(key, hashes.SHA256()))
            pem = cert.public_bytes(serialization.Encoding.PEM)
            row = Certificate(
                refid=str(uuid.uuid4())[:8], descr=cn, subject_cn=cn, subject=f'CN={cn}',
                crt=base64.b64encode(pem).decode(),
                serial_number=format(cert.serial_number, 'X'),
                valid_from=now - timedelta(hours=1), valid_to=now + timedelta(days=365),
                source=source,
            )
            db.session.add(row)
            db.session.flush()
            ids.append(row.id)
        db.session.commit()
    return ids


def _sources_in(resp):
    return {c.get('source') for c in get_json(resp).get('data', [])}


class TestSourceFilter:

    def test_filter_single_source_msca(self, app, auth_client):
        _seed(app, [('srcflt-msca-1.test', 'msca'), ('srcflt-acme-1.test', 'acme')])
        r = auth_client.get(f'{BASE}?source=msca&per_page=100')
        assert r.status_code == 200
        data = get_json(r)['data']
        cns = [(c.get('common_name') or c.get('subject_cn')) for c in data]
        assert 'srcflt-msca-1.test' in cns
        assert 'srcflt-acme-1.test' not in cns
        assert _sources_in(r) <= {'msca'}

    def test_filter_multi_source(self, app, auth_client):
        _seed(app, [('srcflt-msca-2.test', 'msca'), ('srcflt-scep-2.test', 'scep'),
                    ('srcflt-manual-2.test', 'manual')])
        r = auth_client.get(f'{BASE}?source=msca&source=scep&per_page=100')
        assert r.status_code == 200
        got = _sources_in(r)
        assert got <= {'msca', 'scep'}
        cns = [(c.get('common_name') or c.get('subject_cn')) for c in get_json(r)['data']]
        assert 'srcflt-manual-2.test' not in cns

    def test_filter_manual_includes_null_source(self, app, auth_client):
        # Legacy row with NULL source must be found under the 'manual' filter.
        ids = _seed(app, [('srcflt-legacy-null.test', 'manual')])
        with app.app_context():
            from models import Certificate, db
            c = db.session.get(Certificate, ids[0])
            c.source = None
            db.session.commit()
        r = auth_client.get(f'{BASE}?source=manual&per_page=100')
        assert r.status_code == 200
        cns = [(c.get('common_name') or c.get('subject_cn')) for c in get_json(r)['data']]
        assert 'srcflt-legacy-null.test' in cns

    def test_no_source_filter_spans_multiple_sources(self, app, auth_client):
        # Filter to just the two seeded sources (deterministic on a shared DB):
        # an unfiltered page-1 assertion would be order/volume dependent.
        _seed(app, [('srcflt-multi-msca.test', 'msca'), ('srcflt-multi-est.test', 'est')])
        r = auth_client.get(f'{BASE}?source=msca&source=est&per_page=100')
        assert r.status_code == 200
        assert _sources_in(r) == {'msca', 'est'}

    def test_stats_exposes_present_sources(self, app, auth_client):
        # The list filter builds its options from the stats 'sources' list, so
        # every source actually present must be advertised there.
        _seed(app, [('srcflt-stats-msca.test', 'msca'), ('srcflt-stats-acme_client.test', 'acme_client')])
        r = auth_client.get(f'{BASE}/stats')
        assert r.status_code == 200
        sources = get_json(r)['data'].get('sources', [])
        assert 'msca' in sources
        assert 'acme_client' in sources  # drifted value still surfaced

    def test_filter_matches_stats_advertised_source(self, app, auth_client):
        # A source advertised by stats must be filterable and return only it.
        _seed(app, [('srcflt-adv-acme_client.test', 'acme_client'),
                    ('srcflt-adv-msca.test', 'msca')])
        r = auth_client.get(f'{BASE}?source=acme_client&per_page=100')
        assert r.status_code == 200
        cns = [(c.get('common_name') or c.get('subject_cn')) for c in get_json(r)['data']]
        assert 'srcflt-adv-acme_client.test' in cns
        assert 'srcflt-adv-msca.test' not in cns
        assert _sources_in(r) <= {'acme_client'}
