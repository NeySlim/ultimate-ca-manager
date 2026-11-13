"""A client of another realm than the accepting key is refused, and the admin guide says so."""
import logging
from pathlib import Path
from types import SimpleNamespace

from services.kerberos.negotiate_auth import _served_realm_matches

GUIDE = Path(__file__).resolve().parents[2] / 'docs' / 'ADMIN_GUIDE.md'


def _server(client, target):
    ctx = SimpleNamespace(target_name=target)
    return SimpleNamespace(client_principal=client, _context=SimpleNamespace(_context=ctx))


def test_child_realm_client_refused_with_logged_line(caplog):
    srv = _server('PC1$@CHILD.CORP.EXAMPLE', 'HTTP/ucm.example.com@CORP.EXAMPLE')
    with caplog.at_level(logging.WARNING):
        assert _served_realm_matches(srv) is False
    assert 'does not match the realm' in caplog.text


def test_same_realm_client_served():
    assert _served_realm_matches(_server('PC1$@CORP.EXAMPLE', 'HTTP/ucm.example.com@CORP.EXAMPLE')) is True


def test_guide_documents_cross_realm_refusal():
    text = GUIDE.read_text()
    assert 'one profile per realm' in text.lower()
    assert 'does not match the realm' in text
    # Child domains and trusts were never benched: the guide must say so, not promise a remedy.
    assert 'child domains of a forest have not been tested' in text
    assert 'give it its own service account' not in text


def _refusal_row(start):
    return next(line for line in GUIDE.read_text().splitlines() if line.startswith(start))


def test_guide_places_keyed_profile_without_realm_in_the_400_row():
    row = _refusal_row('| A profile holds the realm')
    assert "holds the realm's key but has no realm" in row
    assert 'HTTP 400' in row


def test_guide_401_row_means_no_key_for_the_realm():
    row = _refusal_row('| No profile holds a key')
    assert 'No profile holds a key for that realm' in row
    assert 'no audit entry' in row


def test_guide_connector_409_says_realm_can_be_cleared():
    text = GUIDE.read_text()
    assert 'whose realm can only be moved to another realm of its keytab or cleared' in text
    assert 'whose realm only its keytab can change' not in text
