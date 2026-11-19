import base64
import logging
import os
import tempfile
from typing import Optional
from models import db
from models.msca import MicrosoftCA, MSCARequest
from utils.datetime_utils import utc_now
from utils.encryption import decrypt_required
from utils.secret_target import MASKS, changed_targets, keeps_saved_secret
from .client_keytab import client_keytab

logger = logging.getLogger(__name__)

# What a form can change in a connection test; the secrets are handled apart
_TESTED_FIELDS = ('server', 'ca_name', 'auth_method', 'username', 'client_cert_pem',
                  'kerberos_principal', 'kerberos_keytab_path', 'use_ssl', 'verify_ssl', 'ca_bundle')
# Where and how a saved secret is sent, and the saved secret of each method. A Kerberos keytab
# path and principal are read back in clear: moving them is a permission (admin:system), not a retype
_TARGET_FIELDS = ('server', 'use_ssl', 'verify_ssl', 'ca_bundle', 'auth_method')
_SAVED_CREDENTIALS = {'basic': (('password', '_password'),),
                      'certificate': (('client_key_pem', '_client_key_pem'),)}


def saved_credential_retargets(msca, overrides):
    """Fields of a test or save that would send a saved secret it did not retype elsewhere.
    A blank value is no secret, never the saved one."""
    method = overrides.get('auth_method', msca.auth_method)
    if not any(keeps_saved_secret(overrides, field, getattr(msca, column), blank_clears=True)
               for field, column in _SAVED_CREDENTIALS.get(method, ())):
        return []
    current = {k: getattr(msca, k) for k in _TARGET_FIELDS}
    if method == 'basic':
        current['username'] = msca.username
    return changed_targets(current, overrides)


class MicrosoftCAConnectionMixin:

    @staticmethod
    def _get_client(msca, typed=False):
        """typed: the secrets come from the form, in plaintext, never decrypted."""
        import certsrv

        server = msca.server
        temp_files = []

        def _secret(stored, what):
            return stored if typed else decrypt_required(stored, f'Microsoft CA {msca.id} {what}')

        def _write_temp(content):
            tmp = tempfile.NamedTemporaryFile(delete=False, suffix='.pem', mode='w')
            tmp.write(content or '')
            tmp.close()
            temp_files.append(tmp.name)
            return tmp.name

        try:
            cafile = None
            if msca.verify_ssl and msca.ca_bundle:
                cafile = _write_temp(msca.ca_bundle)

            if msca.auth_method == 'certificate':
                cert_path = _write_temp(msca.client_cert_pem)
                key_path = _write_temp(_secret(msca._client_key_pem, 'client key'))

                client = certsrv.Certsrv(
                    server=server,
                    username=cert_path,
                    password=key_path,
                    auth_method='cert',
                    cafile=cafile,
                )

            elif msca.auth_method == 'kerberos':
                try:
                    from requests_kerberos import HTTPKerberosAuth, OPTIONAL
                except ImportError:
                    raise RuntimeError(
                        "requests-kerberos package not installed. "
                        "Install with: pip install requests-kerberos"
                    )

                # KRB5_KTNAME is the acceptor's keytab: a client never writes it (A12)
                keytab = msca.kerberos_keytab_path or None
                principal = msca.kerberos_principal or None

                class _ConnectionKerberosAuth(HTTPKerberosAuth):
                    # The credential is acquired here: the connection keytab is named only meanwhile
                    def generate_request_header(self, *args, **kwargs):
                        with client_keytab(keytab, principal=principal, owner=msca.id):
                            return super().generate_request_header(*args, **kwargs)

                # auth_method='basic' is a placeholder: the real auth is the
                # Kerberos handler set below. 'ntlm' would make certsrv import
                # requests_ntlm, which is neither installed nor used here.
                client = certsrv.Certsrv(
                    server=server,
                    username='',
                    password='',
                    auth_method='basic',
                    cafile=cafile,
                )
                # principal selects the credential in the cache or keytab (None: default)
                client.session.auth = _ConnectionKerberosAuth(
                    mutual_authentication=OPTIONAL,
                    principal=principal,
                )

            elif msca.auth_method == 'basic':
                client = certsrv.Certsrv(
                    server=server,
                    username=msca.username or '',
                    password=_secret(msca._password, 'password') or '',
                    auth_method='basic',
                    cafile=cafile,
                )

            else:
                raise ValueError(f"Unsupported auth method: {msca.auth_method}")

            if not msca.verify_ssl:
                client.session.verify = False

            client._temp_files = temp_files
            return client

        except Exception:
            # Client cert/key PEMs land in temp files — never leave them behind
            for f in temp_files:
                try:
                    os.unlink(f)
                except OSError:
                    pass
            raise

    @staticmethod
    def _cleanup_client(client):
        for f in getattr(client, '_temp_files', []):
            try:
                os.unlink(f)
            except OSError:
                pass

    @staticmethod
    def _with_form_values(msca, overrides):
        """The saved connection under the form's values: what a test runs on, never persisted.
        A secret left out or masked is the saved one, decrypted, and only for the saved target."""
        from types import SimpleNamespace
        if saved_credential_retargets(msca, overrides):
            raise ValueError('A saved credential is not sent to another target')
        values = {k: getattr(msca, k) for k in _TESTED_FIELDS}
        values.update({k: v for k, v in overrides.items() if k in _TESTED_FIELDS})
        for field, column in (('password', '_password'), ('client_key_pem', '_client_key_pem')):
            typed = overrides.get(field)
            if isinstance(typed, str) and typed.strip() and typed.strip() not in MASKS:
                secret = typed
            elif not keeps_saved_secret(overrides, field, getattr(msca, column), blank_clears=True):
                secret = ''
            else:
                secret = decrypt_required(getattr(msca, column), f'Microsoft CA {msca.id} {field}') \
                    if getattr(msca, column) else ''
            values[field] = secret
            values[column] = secret
        return SimpleNamespace(id=msca.id, name=msca.name, **values)

    @staticmethod
    def test_connection(msca_id, overrides=None):
        """overrides: form values to test instead of the saved ones; nothing is saved then."""
        from .templates import MicrosoftCATemplatesMixin

        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            return {'success': False, 'error': 'Connection not found'}

        client = None
        try:
            if overrides:
                tested = MicrosoftCAConnectionMixin._with_form_values(msca, overrides)
                client = MicrosoftCAConnectionMixin._get_client(tested, typed=True)
            else:
                tested = msca
                client = MicrosoftCAConnectionMixin._get_client(msca)
            ca_cert = client.get_ca_cert()

            templates = []
            permissions_ok = False
            permission_warning = None
            try:
                templates = MicrosoftCATemplatesMixin._get_templates(client)
                templates = sorted(templates) if templates else []
                permissions_ok = len(templates) > 0
                if not permissions_ok:
                    permission_warning = 'authenticated_but_no_templates'
            except Exception as tpl_err:
                permission_warning = 'authenticated_but_template_access_denied'
                logger.warning(
                    f"MS CA '{msca.name}': auth OK but template listing failed: {tpl_err}"
                )

            if not overrides:
                msca.last_test_at = utc_now()
                msca.last_test_result = 'success' if permissions_ok else 'partial'
                try:
                    db.session.commit()
                except Exception as commit_err:
                    db.session.rollback()
                    logger.error(f"MS CA test result commit failed: {commit_err}")

            result = {
                'success': True,
                'ca_name': tested.ca_name or tested.server,
                'ca_cert_available': ca_cert is not None,
                'templates': templates,
                'permissions_ok': permissions_ok,
            }
            if permission_warning:
                result['warning'] = permission_warning
            return result
        except Exception as e:
            logger.error(f"MS CA connection test failed for '{msca.name}': {e}")
            if not overrides:
                msca.last_test_at = utc_now()
                msca.last_test_result = f'failed: {str(e)[:200]}'
                try:
                    db.session.commit()
                except Exception as commit_err:
                    db.session.rollback()
                    logger.error(f"MS CA test result commit failed: {commit_err}")
            return {'success': False, 'error': str(e)}
        finally:
            if client:
                MicrosoftCAConnectionMixin._cleanup_client(client)

    @staticmethod
    def test_connection_inline(data):
        from types import SimpleNamespace
        from .templates import MicrosoftCATemplatesMixin

        # _get_client reads the stored columns (_password, _client_key_pem) and id; here they
        # hold the plaintext typed in the form, used as typed even when it looks like a token.
        fake_msca = SimpleNamespace(
            id='unsaved',
            _password=data.get('password', ''),
            _client_key_pem=data.get('client_key_pem', ''),
            server=data.get('server', ''),
            ca_name=data.get('ca_name', ''),
            auth_method=data.get('auth_method', 'basic'),
            username=data.get('username', ''),
            password=data.get('password', ''),
            client_cert_pem=data.get('client_cert_pem', ''),
            client_key_pem=data.get('client_key_pem', ''),
            kerberos_principal=data.get('kerberos_principal', ''),
            kerberos_keytab_path=data.get('kerberos_keytab_path', ''),
            use_ssl=data.get('use_ssl', True),
            verify_ssl=data.get('verify_ssl', True),
            ca_bundle=data.get('ca_bundle', ''),
        )
        client = None
        try:
            client = MicrosoftCAConnectionMixin._get_client(fake_msca, typed=True)
            client.get_ca_cert()

            templates = []
            permission_warning = None
            try:
                templates = MicrosoftCATemplatesMixin._get_templates(client)
                templates = sorted(templates) if templates else []
                if not templates:
                    permission_warning = 'authenticated_but_no_templates'
            except Exception:
                permission_warning = 'authenticated_but_template_access_denied'

            result = {
                'success': True,
                'templates': templates,
                'permissions_ok': len(templates) > 0,
            }
            if permission_warning:
                result['warning'] = permission_warning
            return result
        except Exception as e:
            logger.error(f"MS CA inline test failed: {e}")
            return {'success': False, 'error': str(e)}
        finally:
            if client:
                MicrosoftCAConnectionMixin._cleanup_client(client)
