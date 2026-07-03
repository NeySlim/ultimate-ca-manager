"""ACME preflight / dry-run validation (issue #162).

Validates domains, CA connectivity, account/EAB, and DNS-01 challenge setup
against the staging Let's Encrypt directory without touching production rate
limits or the globally configured production account.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional, Tuple

from models import db, DnsProvider, SystemConfig
from models.acme_client_account import AcmeClientAccount
from models.acme_models import AcmeClientOrder
from services.acme.acme_client_service import AcmeClientService
from utils.dns_txt_lookup import txt_record_present

logger = logging.getLogger(__name__)

KEY_SOURCE_VALUES = frozenset({'generate', 'reuse', 'csr'})


def _step(name: str, label: str, ok: bool, detail: str = '', data: Optional[dict] = None) -> dict:
    return {
        'name': name,
        'label': label,
        'status': 'pass' if ok else 'fail',
        'detail': detail,
        'data': data or {},
    }


def _resolve_staging_client(acme_account_id: Optional[int]) -> Tuple[Optional[AcmeClientService], str]:
    """Build an ACME client pointed at staging (never production)."""
    if acme_account_id:
        acct = AcmeClientAccount.query.get(acme_account_id)
        if acct:
            if acct.directory_url == AcmeClientAccount.LE_PRODUCTION_URL:
                staging = AcmeClientAccount.query.filter_by(
                    directory_url=AcmeClientAccount.LE_STAGING_URL
                ).first()
                if staging:
                    return AcmeClientService(account=staging), 'staging'
                return AcmeClientService(environment='staging'), 'staging'
            if acct.directory_url == AcmeClientAccount.LE_STAGING_URL:
                return AcmeClientService(account=acct), 'staging'
            # Custom CA — no staging twin; connectivity-only against configured URL.
            return AcmeClientService(account=acct), 'custom'
    return AcmeClientService(environment='staging'), 'staging'


class AcmePreflightService:
    """Run preflight checks for an ACME certificate request."""

    @classmethod
    def run(
        cls,
        *,
        domains: List[str],
        email: str,
        challenge_type: str = 'dns-01',
        dns_provider_id: Optional[int] = None,
        acme_account_id: Optional[int] = None,
        key_source: str = 'generate',
        csr_pem: Optional[str] = None,
        verify_dns: bool = False,
        mode: str = 'full',
    ) -> Dict[str, Any]:
        """
        Execute preflight steps and return a structured report.

        mode:
          - ``full``: create a staging ACME order to preview challenges (LE only).
          - ``validate_only``: skip order creation; check config + connectivity.
        """
        steps: List[dict] = []
        overall_ok = True
        staging_order: Optional[AcmeClientOrder] = None
        challenge_preview: dict = {}

        # --- domains ---
        if not domains:
            steps.append(_step('domains', 'Domain list', False, 'At least one domain is required'))
            overall_ok = False
        else:
            import re as _re
            _label = r'(?!-)[A-Za-z0-9-]{1,63}(?<!-)'
            _fqdn_re = _re.compile(rf'^(\*\.)?({_label}\.)+{_label}$')
            bad = [d for d in domains if not isinstance(d, str) or not _fqdn_re.match(d)]
            has_wildcard = any(d.startswith('*.') for d in domains)
            wildcard_ok = not (has_wildcard and challenge_type != 'dns-01')
            dom_ok = not bad and wildcard_ok
            detail = 'OK'
            if bad:
                detail = f'Invalid domain syntax: {", ".join(bad[:5])}'
            elif not wildcard_ok:
                detail = 'Wildcard domains require DNS-01 challenge'
            steps.append(_step('domains', 'Domain validation', dom_ok, detail, {'domains': domains}))
            overall_ok = overall_ok and dom_ok

        # --- email ---
        email_ok = bool(email and '@' in email)
        if not email_ok:
            email_cfg = SystemConfig.query.filter_by(key='acme.client.email').first()
            email = email_cfg.value if email_cfg else None
            email_ok = bool(email and '@' in email)
        steps.append(_step(
            'email', 'Contact email',
            email_ok,
            email if email_ok else 'Email required in request or ACME settings',
        ))
        overall_ok = overall_ok and email_ok

        # --- key source / CSR ---
        ks = (key_source or 'generate').lower()
        if ks not in KEY_SOURCE_VALUES:
            steps.append(_step('key_source', 'Key source', False, f'Invalid key_source: {key_source}'))
            overall_ok = False
        elif ks == 'csr':
            if not csr_pem:
                steps.append(_step('csr', 'External CSR', False, 'CSR PEM required when key_source is csr'))
                overall_ok = False
            else:
                try:
                    from utils.acme_csr import load_pem_csr, csr_domains_match_order
                    csr = load_pem_csr(csr_pem)
                    match_ok, match_msg = csr_domains_match_order(csr, domains)
                    steps.append(_step('csr', 'External CSR', match_ok, match_msg))
                    overall_ok = overall_ok and match_ok
                except ValueError as exc:
                    steps.append(_step('csr', 'External CSR', False, str(exc)))
                    overall_ok = False
        else:
            label = 'Reuse key on renewal' if ks == 'reuse' else 'Generate new key'
            steps.append(_step('key_source', 'Key source', True, label))

        # --- DNS provider ---
        provider = None
        manual_dns = False
        if challenge_type == 'dns-01':
            if dns_provider_id:
                provider = DnsProvider.query.get(dns_provider_id)
                if not provider:
                    steps.append(_step('dns_provider', 'DNS provider', False, 'DNS provider not found'))
                    overall_ok = False
                elif not provider.enabled:
                    steps.append(_step('dns_provider', 'DNS provider', False, 'DNS provider is disabled'))
                    overall_ok = False
                else:
                    manual_dns = provider.provider_type == 'manual'
                    steps.append(_step(
                        'dns_provider', 'DNS provider', True,
                        f'{provider.name} ({provider.provider_type})',
                        {'provider_id': provider.id, 'manual': manual_dns},
                    ))
            else:
                manual_dns = True
                steps.append(_step(
                    'dns_provider', 'DNS provider', True,
                    'Manual DNS (no automated provider selected)',
                    {'manual': True},
                ))
        else:
            steps.append(_step('dns_provider', 'DNS provider', True, 'Not required for HTTP-01'))

        # --- CA connectivity + account ---
        client, env_kind = _resolve_staging_client(acme_account_id)
        try:
            directory = client._fetch_directory()
            steps.append(_step(
                'ca_connectivity', 'CA directory',
                True,
                f'Reachable ({client.directory_url})',
                {'environment': env_kind, 'directory_url': client.directory_url},
            ))
        except Exception as exc:
            steps.append(_step('ca_connectivity', 'CA directory', False, str(exc)))
            overall_ok = False
            directory = None

        account_ok = False
        account_detail = ''
        if directory is not None and email_ok:
            try:
                reg_ok, reg_msg = client.ensure_account(email)
                account_ok = reg_ok
                account_detail = reg_msg
                acct = client.account
                eab_required = bool(getattr(acct, 'eab_kid', None) is None and directory.get('meta', {}).get('externalAccountRequired'))
                if acct and acct.eab_kid:
                    eab_required = False
                if directory.get('meta', {}).get('externalAccountRequired') and not (acct and acct.eab_kid):
                    account_ok = False
                    account_detail = 'External Account Binding required but not configured'
            except Exception as exc:
                account_detail = str(exc)
            steps.append(_step(
                'account_eab', 'ACME account / EAB',
                account_ok,
                account_detail,
                {'registered': account_ok},
            ))
            overall_ok = overall_ok and account_ok

        # --- staging order + challenge preview (full mode, LE staging) ---
        can_create_order = (
            mode == 'full'
            and overall_ok
            and directory is not None
            and email_ok
            and env_kind in ('staging',)
        )
        if mode == 'full' and env_kind == 'custom':
            steps.append(_step(
                'challenge_preview', 'Challenge preview',
                True,
                'Skipped — custom CA has no staging endpoint; connectivity validated only',
            ))
        elif can_create_order:
            try:
                ok, msg, staging_order = client.create_order(
                    domains=domains,
                    email=email,
                    challenge_type=challenge_type,
                    dns_provider_id=dns_provider_id,
                )
                if not ok or not staging_order:
                    steps.append(_step('challenge_preview', 'Staging order', False, msg))
                    overall_ok = False
                else:
                    staging_order.key_source = ks
                    if csr_pem and ks == 'csr':
                        staging_order.csr_pem = csr_pem
                    db.session.commit()

                    if challenge_type == 'dns-01':
                        setup_ok, setup_msg, challenge_info = client.setup_dns_challenge(staging_order)
                        challenge_preview = challenge_info or staging_order.challenges_dict
                        txt_records = [
                            {
                                'domain': d,
                                'name': c.get('dns_txt_name'),
                                'value': c.get('dns_txt_value'),
                            }
                            for d, c in challenge_preview.items()
                            if c.get('dns_txt_value')
                        ]
                        ch_ok = setup_ok or manual_dns
                        detail = setup_msg if not setup_ok else (
                            'TXT records computed' + ('; automated create attempted' if not manual_dns else '')
                        )
                        steps.append(_step(
                            'challenge_setup', 'DNS-01 challenge',
                            ch_ok, detail,
                            {'txt_records': txt_records},
                        ))
                        overall_ok = overall_ok and ch_ok

                        if verify_dns and txt_records:
                            verified = []
                            missing = []
                            for rec in txt_records:
                                if txt_record_present(rec['name'], rec['value']):
                                    verified.append(rec['domain'])
                                else:
                                    missing.append(rec['domain'])
                            dns_ok = not missing
                            steps.append(_step(
                                'dns_propagation', 'DNS TXT propagation',
                                dns_ok,
                                'All TXT records visible' if dns_ok else f'Not visible for: {", ".join(missing)}',
                                {'verified': verified, 'missing': missing},
                            ))
                            overall_ok = overall_ok and dns_ok

                        if not manual_dns and provider and setup_ok:
                            try:
                                client.cleanup_dns_challenge(staging_order)
                            except Exception as cleanup_err:
                                logger.debug('Preflight DNS cleanup: %s', cleanup_err)
                    else:
                        steps.append(_step(
                            'challenge_setup', f'{challenge_type} challenge',
                            True,
                            'Staging order created; finalize not attempted',
                            {'order_id': staging_order.id},
                        ))

                    # Remove ephemeral staging order from DB — preflight only.
                    try:
                        db.session.delete(staging_order)
                        db.session.commit()
                    except Exception as del_err:
                        db.session.rollback()
                        logger.warning('Could not delete preflight staging order: %s', del_err)
            except Exception as exc:
                logger.error('Preflight staging order failed: %s', exc, exc_info=True)
                steps.append(_step('challenge_preview', 'Staging order', False, str(exc)))
                overall_ok = False
        elif mode == 'validate_only':
            steps.append(_step(
                'challenge_preview', 'Challenge preview',
                True,
                'Validation-only mode — no staging order created',
            ))

        return {
            'ok': overall_ok,
            'mode': mode,
            'staging_environment': env_kind,
            'steps': steps,
            'txt_records': [
                {'domain': d, 'name': c.get('dns_txt_name'), 'value': c.get('dns_txt_value')}
                for d, c in challenge_preview.items()
                if c.get('dns_txt_value')
            ],
        }
