"""A fresh install seeds its system templates from TemplateService.SYSTEM_TEMPLATES, the one list."""
from tests.fresh_app import fresh_app


def test_fresh_install_seeds_the_one_system_template_list(monkeypatch):
    from services.template_service import TemplateService
    marked = [{**t, 'key_type': 'RSA-3072'} for t in TemplateService.SYSTEM_TEMPLATES]
    monkeypatch.setattr(TemplateService, 'SYSTEM_TEMPLATES', marked)
    with fresh_app() as application:
        from models.certificate_template import CertificateTemplate
        with application.app_context():
            seeded = {t.name: t.key_type for t in CertificateTemplate.query.filter_by(is_system=True)}
    assert seeded == {t['name']: 'RSA-3072' for t in marked}
