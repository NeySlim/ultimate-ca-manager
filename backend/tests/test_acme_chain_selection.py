"""Tests for RFC 8555 alternate chain selection (preferred_chain)."""
from datetime import timedelta

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID

from services.acme.acme_chain_selection import (
    chain_issuer_serials,
    chain_matches_preferred_cn,
    chain_root_common_name,
    collect_link_header_values,
    parse_link_rel_alternate,
    rebuild_acme_chain,
    select_acme_certificate_chain,
    split_pem_certificates,
)
from utils.datetime_utils import utc_now


@pytest.fixture
def custom_ca_account(app):
    import uuid

    from models import AcmeClientAccount, db

    suffix = uuid.uuid4().hex[:8]
    with app.app_context():
        acct = AcmeClientAccount(
            directory_url=f'https://acme-{suffix}.example/directory',
            label='Test CA',
            email='ops@example.com',
        )
        db.session.add(acct)
        db.session.commit()
        acct_id = acct.id
    with app.app_context():
        yield db.session.get(AcmeClientAccount, acct_id)


def _cert_pem(cn: str, issuer_cn: str | None = None) -> bytes:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now = utc_now()
    subject = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    issuer_name = (
        x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, issuer_cn)])
        if issuer_cn
        else subject
    )
    cert = (
        x509.CertificateBuilder()
        .subject_name(subject)
        .issuer_name(issuer_name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(hours=1))
        .not_valid_after(now + timedelta(days=365))
        .sign(key, hashes.SHA256())
    )
    return cert.public_bytes(serialization.Encoding.PEM)


def _chain_pem(leaf_cn: str, root_cn: str) -> str:
    root = _cert_pem(root_cn)
    leaf = _cert_pem(leaf_cn, root_cn)
    return (leaf + root).decode()


def _chain_pem_with_intermediate(leaf_cn: str, intermediate_cn: str, root_cn: str) -> str:
    root = _cert_pem(root_cn)
    intermediate = _cert_pem(intermediate_cn, root_cn)
    leaf = _cert_pem(leaf_cn, intermediate_cn)
    return (leaf + intermediate + root).decode()


def _issuer_chain_pem(intermediate_cn: str, root_cn: str) -> str:
    root = _cert_pem(root_cn)
    intermediate = _cert_pem(intermediate_cn, root_cn)
    return (intermediate + root).decode()


def _short_chain_pem(leaf_cn: str, intermediate_cn: str, root_cn: str) -> str:
    """Chain ending at intermediate; self-signed root omitted from PEM."""
    intermediate = _cert_pem(intermediate_cn, root_cn)
    leaf = _cert_pem(leaf_cn, intermediate_cn)
    return (leaf + intermediate).decode()


class TestLinkParsing:
    def test_parse_single_alternate(self):
        link = '<https://acme.example/cert/alt>;rel="alternate"'
        assert parse_link_rel_alternate(link) == ['https://acme.example/cert/alt']

    def test_parse_multiple_and_dedupe(self):
        link = (
            '<https://acme.example/a>;rel="alternate", '
            '<https://acme.example/a>;rel="alternate", '
            '<https://acme.example/b>;rel="alternate"'
        )
        assert parse_link_rel_alternate(link) == [
            'https://acme.example/a',
            'https://acme.example/b',
        ]

    def test_parse_ignores_other_relations(self):
        link = (
            '<https://acme.example/up>;rel="up", '
            '<https://acme.example/alt>;rel="alternate"'
        )
        assert parse_link_rel_alternate(link) == ['https://acme.example/alt']

    def test_collect_link_header_values_from_mapping(self):
        headers = {'Link': '<https://x/1>;rel="alternate"'}
        assert collect_link_header_values(headers) == ['<https://x/1>;rel="alternate"']


class TestChainHelpers:
    def test_split_pem_certificates(self):
        chain = _chain_pem('leaf.example', 'Root CA')
        blocks = split_pem_certificates(chain)
        assert len(blocks) == 2
        assert blocks[0].startswith('-----BEGIN CERTIFICATE-----')

    def test_chain_root_common_name(self):
        chain = _chain_pem('leaf.example', 'ISRG Root X2')
        assert chain_root_common_name(chain) == 'ISRG Root X2'

    def test_chain_matches_preferred_cn_via_issuer_when_root_omitted(self):
        short = _short_chain_pem('leaf.example', 'R3', 'ISRG Root X1')
        assert chain_root_common_name(short) == 'R3'
        assert chain_matches_preferred_cn(short, 'ISRG Root X1')


class TestSelectAcmeCertificateChain:
    def test_no_preference_returns_default(self):
        default = _chain_pem('leaf.example', 'ISRG Root X1')
        result = select_acme_certificate_chain(
            default,
            '<https://acme.example/alt>;rel="alternate"',
            None,
            lambda _url: pytest.fail('should not fetch'),
        )
        assert result == default

    def test_preference_skips_fetch_without_link_headers(self):
        default = _chain_pem('leaf.example', 'ISRG Root X1')

        result = select_acme_certificate_chain(
            default,
            None,
            'ISRG Root X1',
            lambda _url: pytest.fail('should not fetch'),
        )
        assert result == default

    def test_matching_default_is_kept_without_fetching_alternates(self):
        default = _chain_pem('leaf.example', 'ISRG Root X1')
        fetched = []

        def fetch(url):
            fetched.append(url)
            return _chain_pem('leaf.example', 'ISRG Root X2')

        result = select_acme_certificate_chain(
            default,
            '<https://acme.example/alt>;rel="alternate"',
            'ISRG Root X1',
            fetch,
        )
        assert result == default
        assert fetched == []

    def test_preference_selects_alternate_chain(self):
        default = _chain_pem('leaf.example', 'ISRG Root X2')
        alternate = _chain_pem('leaf.example', 'ISRG Root X1')
        alt_url = 'https://acme.example/cert/alt'

        def fetch(url):
            assert url == alt_url
            return alternate

        result = select_acme_certificate_chain(
            default,
            f'<{alt_url}>;rel="alternate"',
            'isrg root x1',
            fetch,
        )
        assert chain_root_common_name(result) == 'ISRG Root X1'
        assert chain_issuer_serials(result) == chain_issuer_serials(alternate)

    def test_preference_not_found_keeps_default(self):
        default = _chain_pem('leaf.example', 'ISRG Root X2')
        alternate = _chain_pem('leaf.example', 'Other Root')

        result = select_acme_certificate_chain(
            default,
            '<https://acme.example/alt>;rel="alternate"',
            'ISRG Root X1',
            lambda _url: alternate,
        )
        assert result == default

    def test_alternate_fetch_failure_still_checks_default(self):
        default = _chain_pem('leaf.example', 'ISRG Root X1')

        def fetch(_url):
            raise RuntimeError('network error')

        result = select_acme_certificate_chain(
            default,
            '<https://acme.example/alt>;rel="alternate"',
            'ISRG Root X1',
            fetch,
        )
        assert result == default

    def test_selects_short_alternate_matching_issuer_cn(self):
        default = _chain_pem('leaf.example', 'ISRG Root X2')
        short_alternate = _short_chain_pem('leaf.example', 'R3', 'ISRG Root X1')

        result = select_acme_certificate_chain(
            default,
            '<https://acme.example/alt>;rel="alternate"',
            'ISRG Root X1',
            lambda _url: short_alternate,
        )
        assert chain_matches_preferred_cn(result, 'ISRG Root X1')
        assert chain_issuer_serials(result) == chain_issuer_serials(
            rebuild_acme_chain(default, short_alternate)
        )

    def test_keeps_default_when_alternate_matches_same_issuers(self):
        default = _chain_pem('leaf.example', 'ISRG Root X1')
        alternate = default

        result = select_acme_certificate_chain(
            default,
            '<https://acme.example/alt>;rel="alternate"',
            'ISRG Root X1',
            lambda _url: alternate,
        )
        assert result == default


class TestRebuildAcmeChain:
    def test_rebuild_issuer_only_alternate(self):
        default = _chain_pem('leaf.example', 'ISRG Root X2')
        issuer_only = _issuer_chain_pem('R3', 'ISRG Root X1')
        rebuilt = rebuild_acme_chain(default, issuer_only)
        blocks = split_pem_certificates(rebuilt)
        assert len(blocks) == 3
        assert chain_root_common_name(rebuilt) == 'ISRG Root X1'
        issuer_serials = lambda pem: tuple(
            x509.load_pem_x509_certificate(b.encode()).serial_number
            for b in split_pem_certificates(pem)
        )
        assert issuer_serials(rebuilt)[1:] == issuer_serials(issuer_only)

    def test_keeps_default_when_alternate_has_same_root_other_intermediates(self):
        default = _chain_pem_with_intermediate('leaf.example', 'Int-Old', 'ISRG Root X1')
        alternate = _chain_pem_with_intermediate('leaf.example', 'Int-New', 'ISRG Root X1')

        result = select_acme_certificate_chain(
            default,
            '<https://acme.example/alt>;rel="alternate"',
            'ISRG Root X1',
            lambda _url: pytest.fail('the default already matches, nothing to fetch'),
        )
        assert result == default


class TestCrossSignedChains:
    """A cross certificate has the subject of its root: only its issuer counts (certbot)."""

    @staticmethod
    def _chains(pki):
        from tests.fixtures.cross_pki import pem
        leaf, int_b = pem(pki.leaf), pem(pki.int_b)
        return {
            'self_signed': leaf + int_b + pem(pki.root_b),
            'root_omitted': leaf + int_b,
            'cross': leaf + int_b + pem(pki.cross_b),
        }

    def test_requesting_root_b_does_not_pick_the_cross_chain(self):
        from tests.fixtures.cross_pki import build_cross_pki
        pki = build_cross_pki()
        chains = self._chains(pki)

        result = select_acme_certificate_chain(
            chains['root_omitted'],
            '<https://acme.example/alt>;rel="alternate"',
            pki.name_b,
            lambda _url: chains['cross'],
        )
        assert result == chains['root_omitted']

    def test_requesting_root_b_leaves_the_cross_chain_for_the_self_signed_one(self):
        from tests.fixtures.cross_pki import build_cross_pki
        pki = build_cross_pki()
        chains = self._chains(pki)

        result = select_acme_certificate_chain(
            chains['cross'],
            '<https://acme.example/alt>;rel="alternate"',
            pki.name_b,
            lambda _url: chains['self_signed'],
        )
        assert result == chains['self_signed']

    def test_requesting_root_a_takes_the_cross_chain(self):
        from tests.fixtures.cross_pki import build_cross_pki
        pki = build_cross_pki()
        chains = self._chains(pki)

        result = select_acme_certificate_chain(
            chains['self_signed'],
            '<https://acme.example/alt>;rel="alternate"',
            pki.name_a,
            lambda _url: chains['cross'],
        )
        assert result == chains['cross']

    def test_cross_chain_as_only_choice_is_kept(self):
        from tests.fixtures.cross_pki import build_cross_pki
        pki = build_cross_pki()
        chains = self._chains(pki)

        result = select_acme_certificate_chain(chains['cross'], None, pki.name_b, lambda _u: '')
        assert result == chains['cross']

    def test_lets_encrypt_2021_alternate_without_the_dst_cross(self):
        """Default ends on ISRG Root X1 cross-signed by DST; the alternate ends on R3."""
        from tests.fixtures.cross_pki import build_cross_pki, make_cert, new_key, pem
        pki = build_cross_pki()
        dst_key, isrg_key, r3_key, leaf_key = (new_key() for _ in range(4))
        isrg_cross = make_cert('ISRG Root X1', isrg_key, 'DST Root CA X3', dst_key)
        r3 = make_cert('R3', r3_key, 'ISRG Root X1', isrg_key, path_length=0)
        leaf = make_cert('le.example', leaf_key, 'R3', r3_key, ca=False, san='le.example')
        default = pem(leaf) + pem(r3) + pem(isrg_cross)
        alternate = pem(leaf) + pem(r3)

        result = select_acme_certificate_chain(
            default, '<https://acme.example/alt>;rel="alternate"', 'ISRG Root X1', lambda _u: alternate)
        assert result == alternate


class TestPreferredChainApi:
    def test_patch_preferred_chain(self, app, auth_client, custom_ca_account):
        resp = auth_client.patch(
            f'/api/v2/acme/client/accounts/{custom_ca_account.id}',
            json={'preferred_chain': '  ISRG Root X1  '},
        )
        assert resp.status_code == 200
        data = resp.get_json()['data']
        assert data['preferred_chain'] == 'ISRG Root X1'

        clear = auth_client.patch(
            f'/api/v2/acme/client/accounts/{custom_ca_account.id}',
            json={'preferred_chain': ''},
        )
        assert clear.status_code == 200
        assert clear.get_json()['data']['preferred_chain'] is None

    def test_patch_preferred_chain_too_long(self, app, auth_client, custom_ca_account):
        resp = auth_client.patch(
            f'/api/v2/acme/client/accounts/{custom_ca_account.id}',
            json={'preferred_chain': 'x' * 256},
        )
        assert resp.status_code == 400
