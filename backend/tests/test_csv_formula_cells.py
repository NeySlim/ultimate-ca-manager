"""The CSV files UCM writes (reports, audit export, discovery export): a text a spreadsheet
would run as a formula (= + - @, tab, carriage return) starts with a quote (OWASP CSV Injection)."""
import csv
import io
import uuid

import pytest

from models import DiscoveredCertificate, db
from utils.csv_cells import csv_cell

FORMULAS = ['=HYPERLINK("http://x.test")', '+1+1', '-2+3', '@SUM(A1)', '\tcmd', '\rcmd', '\n=SUM(A1)',
            '\uff1dSUM(A1)', '\uff0b1', '\uff0d1', '\uff20SUM(A1)']


@pytest.mark.parametrize('value', FORMULAS)
def test_a_formula_text_gets_a_quote(value):
    assert csv_cell(value) == "'" + value


@pytest.mark.parametrize('value', ['plain', 'a=b', '', None, -5, 3.5, True, ' =x'])
def test_any_other_value_is_kept(value):
    assert csv_cell(value) == value


def _read(text):
    return list(csv.reader(io.StringIO(text)))


def test_the_report_csv_neutralises_its_cells():
    from services.report_service import ReportService
    text = ReportService._to_csv([{'name': '=1+1', 'count': -3, 'tags': ['a']}], ['name', 'count', 'tags'])
    assert _read(text)[1] == ["'=1+1", '-3', '["a"]']


def test_the_audit_csv_neutralises_its_cells(app):
    from services.audit_service import AuditService
    action = f'csv_formula_{uuid.uuid4().hex[:8]}'
    with app.app_context():
        AuditService.log_action(action=action, resource_type='test', details='=cmd|"/c calc"!A1',
                                username='@admin')
        text = AuditService.export_logs(format='csv', action=action)
    rows = _read(text)
    assert len(rows) == 2, rows
    header, row = rows
    assert row[header.index('details')] == "'=cmd|\"/c calc\"!A1"
    assert row[header.index('username')] == "'@admin"


@pytest.fixture
def formula_discovered(app):
    tag = uuid.uuid4().hex[:8]
    with app.app_context():
        row = DiscoveredCertificate(target=f'host-{tag}.example.test', port=443, status='unmanaged',
                                    subject=f'=HYPERLINK("http://x.test","{tag}")',
                                    issuer='+evil', fingerprint_sha256=uuid.uuid4().hex * 2)
        db.session.add(row)
        db.session.commit()
        row_id = row.id
    yield tag
    with app.app_context():
        db.session.delete(db.session.get(DiscoveredCertificate, row_id))
        db.session.commit()


def test_the_discovery_csv_neutralises_its_cells(auth_client, formula_discovered):
    r = auth_client.get(f'/api/v2/discovery/export?format=csv&search=host-{formula_discovered}')
    assert r.status_code == 200, r.data
    rows = list(csv.DictReader(io.StringIO(r.get_data(as_text=True))))
    assert [(x['subject'], x['issuer']) for x in rows] == [
        (f'\'=HYPERLINK("http://x.test","{formula_discovered}")', "'+evil")]
