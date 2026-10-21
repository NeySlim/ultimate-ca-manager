"""Compliance preflight from the API and the command line."""
import base64
import json
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from cryptography import x509
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.x509.oid import NameOID
from flask import Flask
from sqlalchemy import text

from models import CA, db
from scripts import compliance_preflight as cli
from tests.test_fips_preflight_api import instance_db  # noqa: F401  (fixture)
from utils.datetime_utils import utc_now

ROUTE = '/api/v2/system/compliance-preflight'
_READ_ONLY_APP = cli.read_only_app
_RSA_2048 = rsa.generate_private_key(public_exponent=65537, key_size=2048)


def _stored_rsa_2048(cn, days):
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, cn)])
    now = datetime.now(timezone.utc)
    cert = (x509.CertificateBuilder().subject_name(name).issuer_name(name)
            .public_key(_RSA_2048.public_key()).serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(days=1)).not_valid_after(now + timedelta(days=days))
            .sign(_RSA_2048, hashes.SHA256()))
    return base64.b64encode(cert.public_bytes(serialization.Encoding.PEM)).decode()


class TestRoute:
    def test_report_shape(self, auth_client):
        response = auth_client.get(f'{ROUTE}?profile=bsi')
        assert response.status_code == 200
        report = response.get_json()['data']
        assert {'profile', 'ca_id', 'ready', 'summary', 'findings', 'errors', 'checked'} <= set(report)
        assert report['profile']['name'] == 'bsi'

    def test_the_ca_scope(self, auth_client, create_ca):
        ca = create_ca()
        response = auth_client.get(f'{ROUTE}?profile=anssi&ca={ca["id"]}')
        assert response.status_code == 200
        assert response.get_json()['data']['ca_id'] == ca['id']

    @pytest.mark.parametrize('query, status', [
        ('', 400), ('?profile=', 400), ('?profile=etsi', 400), ('?profile=bsi&ca=abc', 400),
        ('?profile=bsi&ca=999999', 404)])
    def test_bad_requests(self, auth_client, query, status):
        assert auth_client.get(f'{ROUTE}{query}').status_code == status

    def test_needs_admin_system(self, viewer_client):
        assert viewer_client.get(f'{ROUTE}?profile=bsi').status_code == 403


def _seed(config, descr, days):
    """A CA in the instance file, through a throwaway app: the command opens it read-only."""
    app = Flask('seed')
    app.config.from_object(config)
    db.init_app(app)
    with app.app_context():
        db.session.add(CA(refid=str(uuid.uuid4()), descr=descr, crt=_stored_rsa_2048(descr, days),
                          prv='key', valid_to=utc_now() + timedelta(days=days)))
        db.session.commit()
        db.session.remove()


class TestCommandLine:
    def _run(self, monkeypatch, capsys, config, *args):
        monkeypatch.setattr(cli, 'read_only_app', lambda: _READ_ONLY_APP(config))
        code = cli.main(list(args))
        return code, capsys.readouterr()

    def test_blockers_exit_1_in_text_and_json(self, instance_db, monkeypatch, capsys):
        _engine, config = instance_db
        _seed(config, 'weak-root', 365)
        code, out = self._run(monkeypatch, capsys, config, '--profile', 'bsi')
        assert code == 1
        assert '[BLOCKER] ca.key_type' in out.out and 'weak-root' in out.out
        code, out = self._run(monkeypatch, capsys, config, '--profile', 'bsi', '--json')
        assert code == 1
        assert json.loads(out.out)['summary']['blocker'] >= 1

    def test_advisories_alone_exit_0(self, instance_db, monkeypatch, capsys):
        _engine, config = instance_db
        _seed(config, 'weak-root', 365)
        code, out = self._run(monkeypatch, capsys, config, '--profile', 'anssi')
        assert code == 0
        assert '[WARNING] ca.key_type.advisory' in out.out

    def test_nothing_found_exits_0(self, instance_db, monkeypatch, capsys):
        _engine, config = instance_db
        code, out = self._run(monkeypatch, capsys, config, '--profile', 'eu-acm')
        assert code == 0
        assert '0 blocker(s)' in out.out

    def test_unknown_ca_exits_2(self, instance_db, monkeypatch, capsys):
        _engine, config = instance_db
        code, out = self._run(monkeypatch, capsys, config, '--profile', 'bsi', '--ca', '77')
        assert code == 2
        assert 'not found' in out.err

    def test_a_check_that_cannot_run_exits_2(self, instance_db, monkeypatch, capsys):
        engine, config = instance_db
        with engine.begin() as connection:
            connection.execute(text('DROP TABLE certificate_templates'))
        code, out = self._run(monkeypatch, capsys, config, '--profile', 'bsi')
        assert code == 2
        assert '[ERROR] templates.key_type' in out.out

    def test_unknown_profile_is_refused_by_the_parser(self, capsys):
        with pytest.raises(SystemExit) as exc:
            cli.main(['--profile', 'etsi'])
        assert exc.value.code == 2
