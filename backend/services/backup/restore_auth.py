"""Authentication-related restore methods mixin for BackupService.

Every section here is applied through `apply_columns`, from the manifest the
export was written from. Two things the hand-written assignments got wrong are
what this file exists to stop doing:

* the secrets were assigned to the *private column* underneath the property
  (`sso._oauth2_client_secret = ...`), which is the column the property
  encrypts into -- so a restored SSO provider held its OAuth2 client secret
  and its LDAP bind password in the clear, and restoring a backup quietly
  removed the at-rest protection of the installation that took it;
* everything the list did not name was dropped: an SSO provider came back
  without its issuer, its JWKS URI, its TLS verification settings or its
  required groups, and an HSM provider had its live `status` reset to
  'unknown' while the target was talking to it.

`plan` is what turns a reference into the row it names *here*; the restore
hands its own down. A section the manifest declares no reference for never
asks the plan anything, so those restorers fall back to an empty plan when
they are called directly.
"""
import base64
import logging
from typing import Dict, Optional

import fips_mode
from models import db

from .errors import BackupSchemaError
from .restore import RestorePlan
from .restore.apply import apply_columns
from .restore_extended import reindex_reference_targets

logger = logging.getLogger(__name__)


def _archived_client_certificate(ac_data: Dict):
    """The bytes an archived authentication certificate holds, or a refusal.

    The certificate a client authenticates with is stored as bytes and travels
    base64-encoded. An archive written before that carries the PEM text
    itself, which is why the text is recognised rather than decoded: it used
    to be fed to the base64 decoder and kept only because the failure was
    caught, and a value that was neither of the two became the UTF-8 bytes of
    whatever it was -- a login certificate nobody could ever present, restored
    as a success.

    Decoded here rather than by `apply_columns`, which would hand the PEM text
    to the base64 decoder exactly as the old restore did.
    """
    value = ac_data.get('cert_pem')
    if not isinstance(value, str) or not value:
        return value
    if value.lstrip().startswith('-----BEGIN'):
        return value.encode('utf-8')
    try:
        return base64.b64decode(value)
    except ValueError as exc:   # binascii.Error is one
        raise BackupSchemaError(
            "Invalid backup: the certificate of authentication certificate "
            f"{ac_data.get('cert_serial')} is neither PEM nor base64. Nothing "
            "has been changed."
        ) from exc


class RestoreAuthMixin:
    def _restore_sso_providers(self, backup_data: Dict, results: Dict,
                               plan: Optional[RestorePlan] = None) -> None:
        """Restore SSO providers from backup data.

        The client secret and the bind password go back through the model's
        properties, which re-encrypt them with *this* installation's key; they
        used to be written straight to the columns those properties encrypt
        into, and landed in the database readable.
        """
        from models.sso import SSOProvider
        plan = plan if plan is not None else RestorePlan()
        for sso_data in backup_data.get('sso_providers', []):
            sso = SSOProvider.query.filter_by(name=sso_data['name']).first()
            if sso is None:
                # name and provider_type are NOT NULL; both are overwritten
                # by apply_columns when the archive carries them.
                sso = SSOProvider(
                    name=sso_data['name'],
                    provider_type=sso_data.get('provider_type', 'oauth2'))
                db.session.add(sso)
            apply_columns(sso, 'sso_providers', sso_data, plan)
            results['sso_providers'] += 1

    def _restore_hsm_providers(self, backup_data: Dict, results: Dict,
                               plan: Optional[RestorePlan] = None) -> None:
        """Restore HSM providers from backup data.

        Three columns were applied and the rest of the row was dropped. One of
        the three was `status`, which the manifest excludes on purpose: it is
        live connection state, and a restore reset it to 'unknown' on a
        provider the target was connected to.
        """
        from models.hsm import HsmProvider
        from .restore_extended import reindex_reference_targets

        plan = plan if plan is not None else RestorePlan.build(backup_data)
        reindex_reference_targets('hsm_providers', plan)
        for hsm_data in backup_data.get('hsm_providers', []):
            hsm = HsmProvider.query.filter_by(name=hsm_data['name']).first()
            if hsm is None:
                # name, type and config are NOT NULL
                hsm = HsmProvider(name=hsm_data['name'],
                                  type=hsm_data.get('type') or 'pkcs11',
                                  config=hsm_data.get('config') or '{}')
                db.session.add(hsm)
            apply_columns(hsm, 'hsm_providers', hsm_data, plan)
            if fips_mode.enabled() and hsm.is_softhsm:
                # Restored as it was: the backup is the operator's, the HSM page flags it
                logger.warning("Restored SoftHSM provider %r in FIPS mode: SoftHSM is not a validated module",
                               hsm.name)
            results['hsm_providers'] += 1

    def _restore_api_keys(self, backup_data: Dict, results: Dict,
                          plan: Optional[RestorePlan] = None) -> None:
        """Restore API keys from backup data.

        The plan's index of the users is taken before the first write, so a
        key belonging to a user this same restore creates used to resolve to
        nothing; the number the row already held was kept as a placeholder and
        `relink_references` repaired it at the end. That number is the
        *source's*, and PostgreSQL refuses it at the moment of the insert --
        the repair never ran, and the whole restore died on a foreign key.

        The index of the users is rebuilt here instead, before the first key
        is applied, so the reference resolves to the row it names.
        """
        from models.api_key import APIKey
        plan = plan if plan is not None else RestorePlan.build(backup_data)
        reindex_reference_targets('api_keys', plan)
        for ak_data in backup_data.get('api_keys', []):
            ak = APIKey.query.filter_by(key_hash=ak_data['key_hash']).first()
            if ak is None:
                # key_hash, user_id, name and permissions are NOT NULL
                ak = APIKey(key_hash=ak_data['key_hash'],
                            user_id=ak_data.get('user_id', 1),
                            name=ak_data.get('name', 'restored'),
                            permissions=ak_data.get('permissions', '[]'))
                db.session.add(ak)
            apply_columns(ak, 'api_keys', ak_data, plan)
            results['api_keys'] += 1

    def _restore_auth_certificates(self, backup_data: Dict, results: Dict,
                                   plan: Optional[RestorePlan] = None) -> None:
        """Restore authentication certificates from backup data.

        The certificate itself is decoded before the row is applied (see
        `_archived_client_certificate`); the index of the users is rebuilt
        first for the same reason as in `_restore_api_keys`.
        """
        from models.auth_certificate import AuthCertificate
        plan = plan if plan is not None else RestorePlan.build(backup_data)
        reindex_reference_targets('auth_certificates', plan)
        for ac_data in backup_data.get('auth_certificates', []):
            ac = AuthCertificate.query.filter_by(
                cert_serial=ac_data['cert_serial']
            ).first()

            row = ac_data
            if 'cert_pem' in ac_data:
                row = dict(ac_data, cert_pem=_archived_client_certificate(ac_data))

            if ac is None:
                # user_id, cert_serial and cert_subject are NOT NULL
                ac = AuthCertificate(
                    cert_serial=ac_data['cert_serial'],
                    user_id=ac_data.get('user_id', 1),
                    cert_subject=ac_data.get('cert_subject', ''))
                db.session.add(ac)
            apply_columns(ac, 'auth_certificates', row, plan)
            results['auth_certificates'] += 1
