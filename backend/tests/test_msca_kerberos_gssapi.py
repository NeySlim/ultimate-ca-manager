"""The Microsoft CA Kerberos sign-in on the real system GSSAPI (MIT krb5), without a KDC.

The realm's KDC is a closed local port: acquiring from a keytab fails at once, and the
signature answers 400 with MIT's own words instead of the 500 a swallowed error became.
"""
import json

import pytest

from tests.keytab_support import keytab
from tests.optional_backends import needs
from tests.test_msca_kerberos_failure import _connection, _csr, ca  # noqa: F401 - fixture
from tests.conftest import get_json

try:
    import gssapi  # noqa: F401
    HAS_GSSAPI = True
except ImportError:
    HAS_GSSAPI = False

pytestmark = [needs('gssapi', HAS_GSSAPI, reason='needs pyspnego[kerberos]'),
              pytest.mark.usefixtures('drop_new_cas_and_certificates')]

KRB5_CONF = """[libdefaults]
  default_realm = ONE.TEST
  dns_lookup_kdc = false
  dns_lookup_realm = false
  dns_canonicalize_hostname = false
  rdns = false
[realms]
  ONE.TEST = {
    kdc = 127.0.0.1:9
  }
"""


@pytest.fixture
def realm(monkeypatch, tmp_path):
    conf = tmp_path / 'krb5.conf'
    conf.write_text(KRB5_CONF)
    monkeypatch.setenv('KRB5_CONFIG', str(conf))
    monkeypatch.delenv('KRB5_CLIENT_KTNAME', raising=False)
    path = tmp_path / 'svc.keytab'
    path.write_bytes(keytab('svc@ONE.TEST'))
    from services.msca import kerberos
    monkeypatch.setattr(kerberos, '_HELD', {})
    return str(path)


def _set(app, msca_id, principal, path):
    from models import db
    from models.msca import MicrosoftCA
    with app.app_context():
        row = db.session.get(MicrosoftCA, msca_id)
        row.kerberos_principal, row.kerberos_keytab_path = principal, path
        db.session.commit()


def _sign(client, msca_id, csr_id):
    return client.post(f'/api/v2/microsoft-cas/{msca_id}/sign/{csr_id}', data=json.dumps({'template': 'WebServer'}),
                       content_type='application/json')


def test_an_unreachable_kdc_is_a_400_naming_it(app, auth_client, ca, realm):  # noqa: F811
    msca_id = _connection(app, 'gss-kdc.test.local', realm)
    _set(app, msca_id, 'svc@ONE.TEST', realm)
    r = _sign(auth_client, msca_id, _csr(app, 'gss-kdc-csr.test.local'))
    assert r.status_code == 400, r.data
    assert "Cannot contact any KDC for realm 'ONE.TEST'" in get_json(r)['message']


def test_a_principal_absent_from_the_keytab_is_a_400_naming_it(app, auth_client, ca, realm):  # noqa: F811
    msca_id = _connection(app, 'gss-absent.test.local', realm)
    _set(app, msca_id, 'absent@ONE.TEST', realm)
    r = _sign(auth_client, msca_id, _csr(app, 'gss-absent-csr.test.local'))
    assert r.status_code == 400, r.data
    assert f'the keytab {realm} holds no key for absent@ONE.TEST' in get_json(r)['message']


def test_an_in_memory_cache_is_destroyed_without_error(realm):
    from services.msca.kerberos import _destroy_ccache
    _destroy_ccache('MEMORY:ucm-msca-test-1')


def test_fips_mode_judges_the_kerberos_library_this_process_loaded():
    """Debian builds libk5crypto with its own cryptography (no libcrypto): FIPS mode refuses it."""
    import os
    from services.msca.kerberos import _mapped_library, fips_crypto_problem
    from utils.elf_needed import needed_libraries
    path = _mapped_library('libk5crypto.so')
    assert path and os.path.isfile(path), path
    on_openssl = any(name.startswith('libcrypto.so') for name in needed_libraries(path))
    assert (fips_crypto_problem() is None) is on_openssl
    if os.path.exists('/etc/debian_version'):
        assert fips_crypto_problem() == f'{path} does its own cryptography, outside the FIPS module'
