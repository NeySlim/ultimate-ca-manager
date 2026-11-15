"""Claims in docs/API_REFERENCE.md checked against the application."""
import json
import os

_REF = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), 'docs', 'API_REFERENCE.md')


def _doc():
    with open(_REF, encoding='utf-8') as fh:
        return fh.read()


def test_protocol_routes_are_registered_and_the_doc_says_so(app):
    rules = {r.rule for r in app.url_map.iter_rules()}
    assert '/tsa' in rules
    assert any(r.startswith('/.well-known/est') for r in rules)
    assert 'is not registered' not in _doc()
