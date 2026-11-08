"""The same omitted field gets the same default, whichever door it came in.

`validity_days` had two defaults for one resource. `POST /api/v2/templates`
created a template with 397 when the field was left out;
`POST /api/v2/templates/import` created it with 365, 442 lines further down
the same file. Export a template that omits the field and import it back and
it is a different template.

The number is not the argument -- 397 is the CA/Browser Forum ceiling for
public TLS and a reasonable thing for a template to default to. Having two
of them, unnamed, in the same file is.

397 was also doing a second job it is unfit for. `CertificateService
.create_certificate` used it as a sentinel meaning "the caller said nothing":

    validity_days = validity_days if validity_days != 397 else ...

so an operator who deliberately typed 397 -- the most likely number for
anyone to type on a TLS certificate, being the published maximum -- had that
choice silently replaced by the template's value.
"""
import json

import pytest

from tests.fixtures.templates import templates_created_here_removed
from utils.validity import (DEFAULT_CERTIFICATE_VALIDITY_DAYS,
                            DEFAULT_TEMPLATE_VALIDITY_DAYS)


@pytest.fixture(autouse=True, scope='module')
def _templates_stay_in_this_module(app):
    with templates_created_here_removed(app):
        yield


def _validity_of(result):
    """Days the issued row was given, whatever shape the service returned."""
    cert = result[0] if isinstance(result, tuple) else result
    if isinstance(cert, dict):
        return cert.get('validity_days')
    days = getattr(cert, 'validity_days', None)
    if days is not None:
        return days
    valid_from = getattr(cert, 'valid_from', None)
    valid_to = getattr(cert, 'valid_to', None)
    if valid_from and valid_to:
        return (valid_to - valid_from).days
    return None

def _make(auth_client, **body):
    body.setdefault('name', 'validity-contract')
    body.setdefault('template_type', 'custom')
    return auth_client.post('/api/v2/templates',
                            data=json.dumps(body),
                            content_type='application/json')


class TestOneDefaultPerResource:
    def test_creating_and_importing_agree(self, auth_client):
        created = _make(auth_client, name='validity-contract-created')
        assert created.status_code in (200, 201), created.data
        made = (created.get_json() or {}).get('data') or {}

        imported = auth_client.post(
            '/api/v2/templates/import',
            data={'json_content': json.dumps([{
                'name': 'validity-contract-imported',
                'template_type': 'custom',
            }])},
            content_type='multipart/form-data')
        assert imported.status_code in (200, 201), imported.data
        assert not (imported.get_json() or {}).get('data', {}).get('skipped'), (
            imported.data)

        listing = (auth_client.get('/api/v2/templates?search=validity-contract-imported')
                   .get_json() or {}).get('data') or []
        rows = listing if isinstance(listing, list) else listing.get('items', [])
        by_name = {row['name']: row for row in rows}
        brought_in = by_name.get('validity-contract-imported')
        assert brought_in is not None, 'the import did not land'

        assert made['validity_days'] == brought_in['validity_days'], (
            'the same template, created and imported with the field left '
            f'out, came out as {made["validity_days"]} and '
            f'{brought_in["validity_days"]} days')

    def test_the_default_is_the_one_that_is_written_down(self, auth_client):
        created = _make(auth_client, name='validity-contract-named')
        made = (created.get_json() or {}).get('data') or {}
        assert made['validity_days'] == DEFAULT_TEMPLATE_VALIDITY_DAYS

    def test_the_column_default_is_the_same_number(self):
        from models.certificate_template import CertificateTemplate
        column = CertificateTemplate.__table__.columns['validity_days']
        assert column.default.arg == DEFAULT_TEMPLATE_VALIDITY_DAYS, (
            'a row created without going through the API would disagree '
            'with one that did')

    def test_the_two_defaults_are_told_apart(self):
        """They are different questions, so they are allowed to differ -- but
        only where each is named."""
        assert DEFAULT_TEMPLATE_VALIDITY_DAYS == 397
        assert DEFAULT_CERTIFICATE_VALIDITY_DAYS == 365


class TestTheCeilingIsNotASentinel:
    def test_asking_for_the_maximum_is_not_asking_for_nothing(
            self, app, create_ca):
        """397 is a number an operator types, not a way of saying nothing."""
        from models import CertificateTemplate, db
        from services.cert_service import CertificateService

        ca = create_ca(cn='Validity Sentinel CA')
        with app.app_context():
            template = CertificateTemplate(
                name='validity-sentinel-template',
                description='',
                template_type='custom',
                key_type='RSA-2048',
                validity_days=30,
                digest='sha256',
                dn_template='{}',
                extensions_template='{}',
                is_system=False,
                is_active=True,
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            result = CertificateService.create_certificate(
                descr='validity-sentinel-cert',
                caref=ca['refid'],
                dn={'CN': 'validity-sentinel.example.com'},
                validity_days=DEFAULT_TEMPLATE_VALIDITY_DAYS,
                template_id=template_id,
            )
            days = _validity_of(result)
        assert days == DEFAULT_TEMPLATE_VALIDITY_DAYS, (
            'the explicit 397 was taken for "nothing said" and replaced by '
            f'the template\'s 30 days: got {days}')

    def test_saying_nothing_still_takes_the_template(self, app, create_ca):
        from models import CertificateTemplate, db
        from services.cert_service import CertificateService

        ca = create_ca(cn='Validity Template CA')
        with app.app_context():
            template = CertificateTemplate(
                name='validity-template-wins',
                description='',
                template_type='custom',
                key_type='RSA-2048',
                validity_days=45,
                digest='sha256',
                dn_template='{}',
                extensions_template='{}',
                is_system=False,
                is_active=True,
            )
            db.session.add(template)
            db.session.commit()
            template_id = template.id

            result = CertificateService.create_certificate(
                descr='validity-template-cert',
                caref=ca['refid'],
                dn={'CN': 'validity-template.example.com'},
                template_id=template_id,
            )
            days = _validity_of(result)
        assert days == 45, (
            f'the template was selected and its 45 days ignored: got {days}')
