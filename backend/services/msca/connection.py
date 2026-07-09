import base64
import logging
import os
import tempfile
from typing import Optional
from models import db
from models.msca import MicrosoftCA, MSCARequest
from utils.datetime_utils import utc_now

logger = logging.getLogger(__name__)


class MicrosoftCAConnectionMixin:

    @staticmethod
    def _get_client(msca):
        import certsrv

        server = msca.server
        temp_files = []

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
                key_path = _write_temp(msca.client_key_pem)

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

                if msca.kerberos_keytab_path:
                    os.environ['KRB5_KTNAME'] = msca.kerberos_keytab_path
                if msca.kerberos_principal:
                    os.environ['KRB5_CLIENT_KTNAME'] = msca.kerberos_keytab_path or ''

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
                client.session.auth = HTTPKerberosAuth(
                    mutual_authentication=OPTIONAL
                )

            elif msca.auth_method == 'basic':
                client = certsrv.Certsrv(
                    server=server,
                    username=msca.username or '',
                    password=msca.password or '',
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
    def test_connection(msca_id):
        from .templates import MicrosoftCATemplatesMixin

        msca = db.session.get(MicrosoftCA, msca_id)
        if not msca:
            return {'success': False, 'error': 'Connection not found'}

        client = None
        try:
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

            msca.last_test_at = utc_now()
            msca.last_test_result = 'success' if permissions_ok else 'partial'
            try:
                db.session.commit()
            except Exception as commit_err:
                db.session.rollback()
                logger.error(f"MS CA test result commit failed: {commit_err}")

            result = {
                'success': True,
                'ca_name': msca.ca_name or msca.server,
                'ca_cert_available': ca_cert is not None,
                'templates': templates,
                'permissions_ok': permissions_ok,
            }
            if permission_warning:
                result['warning'] = permission_warning
            return result
        except Exception as e:
            logger.error(f"MS CA connection test failed for '{msca.name}': {e}")
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

        fake_msca = SimpleNamespace(
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
            client = MicrosoftCAConnectionMixin._get_client(fake_msca)
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
