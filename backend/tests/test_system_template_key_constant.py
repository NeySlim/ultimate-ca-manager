"""System templates take their key type from the one baseline constant, not a literal."""
import importlib

from services import template_service
from utils import issuance_defaults


def test_system_templates_follow_the_baseline_constant(monkeypatch):
    monkeypatch.setattr(issuance_defaults, 'BASELINE_ISSUE_KEY', 'RSA-3072')
    try:
        reloaded = importlib.reload(template_service)
        assert {t['key_type'] for t in reloaded.TemplateService.SYSTEM_TEMPLATES} == {'RSA-3072'}
    finally:
        monkeypatch.undo()
        importlib.reload(template_service)
