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
    assert 'have not been tested' not in text
    assert 'A forest needs one profile' not in text
