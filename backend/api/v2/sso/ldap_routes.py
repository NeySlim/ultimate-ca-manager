from . import bp, VALID_ROLES, logger
from .connection_tests import ATTEMPT_REFUSED, GROUPS_UNREADABLE, _ldap_authenticate_user
from flask import request, session
from auth.unified import require_auth
from auth.session_start import begin_session
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, User, UserSSOIdentity
from models.sso import SSOProvider, SSOSession
from services.audit_service import AuditService
from utils.datetime_utils import utc_now

# Import limiter for rate limiting login attempts
try:
    from app import limiter
    HAS_LIMITER = True
except ImportError:
    HAS_LIMITER = False
from datetime import timedelta
import ldap3
from ldap3 import Server, Connection, ALL, Tls
from ldap3.utils.conv import escape_filter_chars
import ssl
from . import saml_sp
from .account_state import (
    SSO_NO_PASSWORD, bounded, describe_conflict, legacy_sso_account, orphan_text, own_identity,
)
from .helpers import _clear_ldap_failed_attempts, _ldap_attempt_failed, _release_ldap_attempt, _reserve_ldap_attempt, _resolve_mapped_roles, _resolve_role, _build_ldap_tls, _decrypt_ldap_password, sso_admission, _mapping_rules, _external_groups
from .diagnostics import GroupSource, refusal_diagnosis

@bp.route('/api/v2/sso/ldap/login', methods=['POST'])
@limiter.limit("5/minute")
def ldap_login():
    """
    Direct LDAP authentication.
    Unlike OAuth2/SAML, LDAP authenticates with username/password directly.

    On refusals this door says more than the password door, on purpose. Every
    message below that names a reason — the account disabled in the directory,
    the account disabled locally, membership of a required group, groups the
    directory would not give — is returned only after ``_ldap_authenticate_user``
    has bound as the user with the password supplied, so the caller has already
    proved it. Before that point the answers match the password door's exactly: "Invalid credentials", 401,
    whether the name exists in the directory or not.

    Do not "align" these on the generic message: the operator is then left
    guessing why a correct password is refused, which is what the reason codes
    were added for. Do not move them earlier either: pre-bind, they would
    become an account oracle. tests/test_auth_failure_messages.py pins the
    wording of both doors and the order the reasons are decided in.
    """

    data = request.get_json()

    if not data or not data.get('username') or not data.get('password'):
        return error_response("Username and password required", 400)

    # Input validation - prevent DoS and normalize input
    username = str(data.get('username')).strip()[:255]  # Max 255 chars
    password = str(data.get('password'))[:4096]  # OWASP recommends max 4096 for password
    provider_id = data.get('provider_id')

    if not username:
        return error_response("Username and password required", 400)

    # Find LDAP provider
    if provider_id:
        provider = db.session.get(SSOProvider, provider_id)
    else:
        # Use first enabled LDAP provider
        provider = SSOProvider.query.filter_by(provider_type='ldap', enabled=True).first()

    if not provider:
        return error_response("No LDAP provider configured", 400)

    if not provider.enabled:
        return error_response("LDAP provider is disabled", 400)

    # Counted after the search and before the bind, on the account the entry resolves to
    # (whatever spelling the filter accepted), so a burst on any node binds at most
    # max_login_attempts times. An entry with no local account yet has no count.
    attempt = {}

    def reserve(identity):
        try:
            attempt['local'], attempt['rank'], attempt['armed'] = _reserve_ldap_attempt(
                _ldap_local_account(provider, identity))
        except Exception as e:
            logger.error(f"Failed to record LDAP login attempt for {username}: {e}", exc_info=True)
            attempt['failed'] = True
            return False
        return attempt['local'] is None or attempt['rank'] is not None

    user_info, error = _ldap_authenticate_user(provider, username, password, before_bind=reserve)
    local, armed = attempt.get('local'), attempt.get('armed')

    if attempt.get('failed'):
        return error_response("Failed to record login attempt", 500)
    if error == ATTEMPT_REFUSED:
        _ldap_attempt_failed(local, armed)
        AuditService.log_action(
            action='login_failure',
            resource_type='user',
            details=f'LDAP login refused for {username} (account locked)',
            success=False,
            username=username
        )
        return error_response("Invalid credentials", 401)

    if error:
        if error == 'account_disabled':
            # Disabled in LDAP, the password proved: never locks the account by itself.
            _release_ldap_attempt(local, armed)
            AuditService.log_action(
                action='login_failure',
                resource_type='user',
                details=f'LDAP account disabled for {username}',
                success=False,
                username=username
            )
            return error_response("This account has been disabled in Active Directory / LDAP", 403)

        if error == 'group_denied':
            # Proved but not in the required groups: never locks the account by itself.
            _release_ldap_attempt(local, armed)
            AuditService.log_action(
                action='login_failure',
                resource_type='user',
                details=f'LDAP login denied: not in required groups for {username}',
                success=False,
                username=username
            )
            return error_response("Access denied: you are not a member of the required group(s)", 403)

        if error == GROUPS_UNREADABLE:
            # The admission needs groups the directory did not give: never "no rule matches".
            _release_ldap_attempt(local, armed)
            logger.warning(f"LDAP login refused for '{username}' via {provider.name}: "
                           f"its groups could not be read from the directory")
            AuditService.log_action(
                action='login_failure',
                resource_type='user',
                details=(f'LDAP login refused for {username} via {provider.name}: '
                         f'its groups could not be read from the directory'),
                success=False,
                username=username
            )
            return error_response("Access denied: your groups could not be read from the directory", 403)

        # Generic auth failure (wrong password, etc.): the reserved attempt stays counted
        _ldap_attempt_failed(local, armed)
        AuditService.log_action(
            action='login_failure',
            resource_type='user',
            details=f'LDAP authentication failed for {username}',
            success=False,
            username=username
        )
        return error_response("Invalid credentials", 401)

    # Create or update user
    group_label = user_info.pop('group_source', None)
    user, error_code = _get_or_create_sso_user(
        provider,
        user_info['username'],
        user_info.get('email', ''),
        user_info.get('fullname', ''),
        user_info,
        group_source=GroupSource(group_label) if group_label else None,
    )

    if not user:
        _release_ldap_attempt(local, armed)
        # The password is proved by now, so the refusal may say why.
        if error_code == USERNAME_CONFLICT:
            return error_response(
                "Sign-in refused: a local account, or one linked to another identity, "
                "already uses this name. An administrator can link the accounts.", 403)
        if error_code == EMAIL_CONFLICT:
            return error_response(
                "Sign-in refused: another account already uses this e-mail address. "
                "Contact your administrator.", 403)
        if error_code == NO_DEFAULT_ROLE:
            return error_response(
                "Access denied: this provider has no default role and no role mapping rule", 403)
        if error_code == UNMAPPED:
            return error_response(
                "Access denied: no role mapping rule of this provider matches your account", 403)
        # Generic message — don't disclose whether the LDAP user exists or whether
        # auto-provisioning is on/off. Details go to logs only.
        if error_code == 'auto_create_disabled':
            logger.warning(
                f"LDAP login refused for '{username}': automatic account creation disabled"
            )
        return error_response("Invalid credentials", 401)

    # SECURITY: Block disabled accounts (admin can disable LDAP users locally)
    if not user.active:
        _release_ldap_attempt(local, armed)
        logger.warning(f"LDAP login blocked: user {username} is disabled")
        AuditService.log_action(
            action='login_failure',
            resource_type='user',
            resource_id=user.id,
            resource_name=user.username,
            details=f'LDAP login blocked: user disabled (via {provider.name})',
            success=False,
            username=username
        )
        return error_response("This account has been disabled", 403)

    # The bind opened the account it was counted on: its count and lock are cleared.
    # Both come from one resolution; they differ only if the accounts changed in between.
    if local is not None and local.id == user.id:
        if not _clear_ldap_failed_attempts(local):
            # A lock this attempt armed stays as stored, the safe side: it is announced
            _ldap_attempt_failed(local, armed)
            return error_response("Failed to update login stats", 500)
    else:
        _release_ldap_attempt(local, armed)

    # Create or update session (deduplicate like OAuth2/SAML)
    session_id = user_info['dn']
    sso_session = SSOSession.query.filter_by(session_id=session_id).first()
    if sso_session:
        sso_session.expires_at = utc_now() + timedelta(hours=8)
    else:
        sso_session = SSOSession(
            user_id=user.id,
            provider_id=provider.id,
            session_id=session_id,
            sso_name_id=user_info.get('uid', session_id),
            expires_at=utc_now() + timedelta(hours=8)
        )
        db.session.add(sso_session)
    ok, _err = safe_commit(logger, "Failed to persist LDAP session")
    if not ok:
        return _err

    # An enrolled second factor is asked, as at the password door.
    from auth.twofa_enforcement import second_factor_methods
    second_factors = second_factor_methods(user)
    if second_factors:
        begin_session(user)
        session['pending_2fa_user_id'] = user.id
        session['pending_2fa_username'] = user.username
        session['pending_2fa_method'] = 'ldap'
        session.permanent = True
        AuditService.log_action(
            action='login_2fa_required',
            resource_type='user',
            resource_id=user.id,
            resource_name=user.username,
            details=f'LDAP password verified via {provider.name}, 2FA required',
            success=True,
            username=user.username
        )
        return success_response(
            data={'requires_2fa': True, 'methods': second_factors,
                  'user': {'id': user.id, 'username': user.username}},
            message='2FA verification required'
        )

    # Establish Flask session under a new identifier (no session fixation)
    _ldap_now = utc_now()
    begin_session(user)
    session['user_id'] = user.id
    session['username'] = user.username
    session['role'] = user.role
    session['auth_method'] = 'ldap'
    session['login_time'] = _ldap_now.isoformat()
    session['last_activity'] = _ldap_now.isoformat()
    session.permanent = True

    # Forced 2FA enrolment (#141): if this provider enforces 2FA and the user
    # has no TOTP yet, flag the session as restricted until enrolment.
    from auth.twofa_enforcement import must_enroll_2fa, ENROLL_SESSION_KEY
    _must_enroll = must_enroll_2fa(user, auth_method='sso', provider=provider)
    if _must_enroll:
        session[ENROLL_SESSION_KEY] = True

    # Audit log LDAP login success
    AuditService.log_action(
        action='login_success',
        resource_type='user',
        resource_id=user.id,
        resource_name=user.username,
        details=f'LDAP login via {provider.name}',
        success=True,
        username=user.username
    )

    # Generate CSRF token
    csrf_token = None
    try:
        from security.csrf import CSRFProtection
        csrf_token = CSRFProtection.generate_token(user.id)
    except ImportError:
        pass

    # Get role permissions
    from auth.permissions import get_effective_permissions
    permissions = get_effective_permissions(user)

    from auth.session_payload import auth_session_payload

    return success_response(
        data=auth_session_payload(
            user, permissions=permissions, auth_method='ldap',
            csrf_token=csrf_token,
            requires_2fa_enrollment=_must_enroll,
        ),
        message='LDAP authentication successful'
    )


def _get_saml_auth(flask_request, provider, relay_state=None, sign_request=False):
    """Build a OneLogin_Saml2_Auth from Flask request and SSO provider config."""
    base = saml_sp.sp_base_url(flask_request)
    sp_cert = sp_key = None
    if sign_request and provider.saml_sign_requests:
        sp_cert, sp_key = saml_sp.load_sp_credentials(provider, with_key=True)
    return saml_sp.Saml2Auth(saml_sp.request_data(flask_request, base),
                             saml_sp.build_settings(provider, base, sp_cert, sp_key))


def _extract_external_id(provider, external_data):
    """Stable, immutable identifier of the directory account, or None.

    OIDC → `sub`; SAML → persistent `NameID`; LDAP → the configured uid attr
    (entryUUID/objectGUID), falling back to the DN. This is the primary key used
    to recognise an SSO account across username/email changes — email is never
    used as an identity key (avoids account pre-hijacking).
    """
    ed = external_data or {}
    ptype = (provider.provider_type or '').lower()
    if ptype == 'oauth2':
        val = ed.get('sub')
    elif ptype == 'saml':
        # Transient NameIDs change every login → not a stable identifier.
        fmt = str(ed.get('name_id_format', '')).lower()
        val = ed.get('name_id') if 'transient' not in fmt else None
    else:  # ldap
        val = ed.get('uid') or ed.get('ldap_uid') or ed.get('dn')
    val = str(val).strip() if val else ''
    return val or None


def _bind_external_id(row, provider, external_id):
    """Bind the stable id to the row (TOFU). Never replaces an id already bound,
    nor takes one another account of this provider owns. True if bound."""
    if not external_id or row.external_id == external_id:
        return True
    username = row.user.username if row.user is not None else '?'
    if row.external_id:
        logger.warning(
            f"SSO external id of '{username}' is already bound; not replacing it")
        return False
    taken = UserSSOIdentity.query.filter(
        UserSSOIdentity.provider_id == provider.id,
        UserSSOIdentity.external_id == external_id,
    ).first()
    if taken is not None and taken is not row:
        logger.warning(
            f"SSO external id {external_id!r} already bound to '{taken.user.username}'; "
            f"not rebinding to '{username}'")
        return False
    row.bind(external_id)
    return True


USERNAME_CONFLICT = 'sso_username_conflict'
EMAIL_CONFLICT = 'sso_email_conflict'
UNMAPPED = 'sso_unmapped'
NO_DEFAULT_ROLE = 'sso_no_default_role'


def _same_idp_orphans(user, provider):
    """Rows of ``user`` a deleted provider for this exact IdP left. Exact key only: a
    UserInfo URL may serve several issuers (one Entra ID endpoint)."""
    key = provider.idp_key()
    return [row for row in user.sso_identities
            if key and row.provider_id is None and row.orphan_of == key]


def _claimable(user, provider):
    """The row of ``user`` an identity whose stable id matches nobody may take: its own
    attachment to this provider not bound yet, else an unbound orphan of this same IdP.
    A row bound to another identity is never taken (OIDC Core §5.7)."""
    own = own_identity(user, provider)
    if own is not None:
        return own if own.external_id is None else None
    return next((row for row in _same_idp_orphans(user, provider) if row.external_id is None), None)


def _adoptable(user, provider):
    """Whether an identity whose stable id matches nobody may claim ``user`` by name.
    An account attached to other providers only is never claimed: an administrator
    attaches this one to it."""
    return _claimable(user, provider) is not None or legacy_sso_account(user)


def _orphan_with_id(provider, external_id):
    """The one row bound to ``external_id`` whose deleted provider served this same IdP,
    on an account not attached to this provider already; None when there is none, or
    several (a stable id is per IdP)."""
    key = provider.idp_key()
    if not key:
        return None
    rows = UserSSOIdentity.query.filter(
        UserSSOIdentity.external_id == external_id,
        UserSSOIdentity.provider_id.is_(None),
        UserSSOIdentity.orphan_of == key).limit(2).all()
    if len(rows) != 1 or own_identity(rows[0].user, provider) is not None:
        return None
    return rows[0]


def _bound_by_dn(provider, external_data, external_id):
    """The row of this LDAP provider bound by its DN fallback, now that the
    directory returns a stable uid for the DN the user bind just proved."""
    from sqlalchemy import func
    dn = str((external_data or {}).get('dn') or '').strip()
    if provider.provider_type != 'ldap' or not dn or dn == external_id:
        return None
    return UserSSOIdentity.query.filter(UserSSOIdentity.provider_id == provider.id,
                                        func.lower(UserSSOIdentity.external_id) == dn.lower()).first()


def _email_unverified(provider, external_data):
    """The OIDC IdP says the e-mail is not verified (some send the claim as a string)."""
    if provider.provider_type != 'oauth2':
        return False
    flag = (external_data or {}).get('email_verified')
    return flag is False or (isinstance(flag, str) and flag.strip().lower() == 'false')


def _refuse(username, details, code):
    logger.warning(details)
    AuditService.log_action(
        action='login_failure',
        resource_type='sso',
        resource_name=username,
        details=details,
        success=False,
        username=username,
    )
    return None, code


def _refuse_username_conflict(provider, username, account):
    state, remedy = describe_conflict(account, provider)
    return _refuse(username, (f"SSO login via {provider.name!r} refused: the name {username!r} "
                              f"belongs to an account it may not open, which {state} ({remedy})"),
                   USERNAME_CONFLICT)


def _refuse_email_conflict(provider, username, email, account, unverified):
    """No second account for an e-mail an account this identity may not open owns."""
    # This provider may adopt it: only a verified e-mail matches it, attaching would not.
    row = _claimable(account, provider) if unverified else None
    if row is not None:
        held = (f"is attached to {provider.name!r}, not bound yet" if row.provider_id is not None
                else f"has {orphan_text(row)}, left by this same IdP")
        state = (f"{held} but the IdP marks the e-mail unverified "
                 f"(email_verified false), so it is not matched by it")
        remedy = "have the IdP verify the e-mail address"
    else:
        state, remedy = describe_conflict(account, provider)
    return _refuse(username, (f"SSO login via {provider.name!r} refused for {username!r}: the e-mail "
                              f"{bounded(email)!r} belongs to the account {account.username!r}, which "
                              f"{state}; no second account is created ({remedy}; for another person, create "
                              f"an account named {username!r} and attach this provider to it, removing "
                              f"its local password)"),
                   EMAIL_CONFLICT)


_GENERIC_SOURCES = {'oauth2': "the IdP's claims", 'saml': 'the assertion', 'ldap': 'the directory'}


def _refuse_unmapped(provider, username, external_data=None, group_source=None):
    """The refusal for want of a role, with the groups read, their source and the remedy."""
    if _mapping_rules(provider):
        reason, code = 'no role mapping rule matches it', UNMAPPED
    else:
        reason, code = 'the provider has no role mapping rule and no default role', NO_DEFAULT_ROLE
    if group_source is None:
        group_source = GroupSource(_GENERIC_SOURCES.get(provider.provider_type, 'the IdP'))
    diagnosis = refusal_diagnosis(_external_groups(external_data), group_source)
    return _refuse(username, f"SSO login via {provider.name!r} refused for {username!r}: "
                             f"{reason}; {diagnosis}", code)


def _email_owner(provider, account, unverified):
    """An account owning the presented e-mail that this identity may not open and whose
    existence a new account would duplicate: one attached to other providers or left by
    another or unknown IdP only, or one this provider may adopt that an unverified e-mail
    cannot match. One bound to another identity of this IdP is another person's."""
    if account.is_local:
        return False  # e-mail is unique among local accounts only (#136)
    if own_identity(account, provider) is None and not _same_idp_orphans(account, provider):
        return True
    return unverified and _claimable(account, provider) is not None


def _resolve_sso_account(provider, username, email, external_data):
    """(account, row, rebind, conflict, email_owner): the local account this identity opens
    and the identity row it opens it with (None: a legacy account gets one), whether that
    row is the DN-bound one moving to the stable uid, the account of the same name it may
    not claim, and the one owning its e-mail it may not claim either.
    Reads only: the LDAP door counts its attempt on what this finds."""
    from sqlalchemy import func
    external_id = _extract_external_id(provider, external_data)

    # 1. Stable-identifier match: robust to username/email changes (primary).
    row = None
    rebind = False
    if external_id:
        row = UserSSOIdentity.query.filter_by(
            provider_id=provider.id, external_id=external_id).first()
        if row is None:
            row = _bound_by_dn(provider, external_data, external_id)
            rebind = row is not None
        if row is None:
            row = _orphan_with_id(provider, external_id)
    if row is not None:
        return row.user, row, rebind, None, None

    # 2. Not bound yet (legacy, or attached by an admin): match by username, but
    #    only an account this identity may claim.
    conflict = None
    user = User.query.filter_by(username=username).first()
    if user is not None:
        if _adoptable(user, provider):
            return user, _claimable(user, provider), False, None, None
        conflict = user

    # 3. An account an admin attached to this provider that owns this email but
    #    whose username differs (#138). Never a local or already bound account,
    #    nor by an e-mail the OIDC IdP says is unverified.
    email_owner = None
    if email:
        unverified = _email_unverified(provider, external_data)
        norm = email.strip().lower()
        candidates = User.query.filter(func.lower(User.email) == norm).order_by(User.id).all()
        if not unverified:
            for candidate in candidates:
                found = _claimable(candidate, provider)
                if found is not None:
                    return candidate, found, False, None, None
        email_owner = next((u for u in candidates if _email_owner(provider, u, unverified)), None)
    return None, None, False, conflict, email_owner


def _ldap_local_account(provider, identity):
    """The local account a bind of this directory entry would open or be refused on."""
    user, _row, _rebind, conflict, _owner = _resolve_sso_account(
        provider, identity['username'], identity.get('email', ''), identity)
    return user or conflict


def _get_or_create_sso_user(provider, username, email, fullname, external_data, group_source=None):
    """Create or update a user from SSO authentication; ``group_source`` says where the
    groups were read, for a refusal for want of a role.

    Returns:
        tuple: (user, error_code) - user object or None, and error code if failed
    """
    external_id = _extract_external_id(provider, external_data)
    user, row, rebind, conflict, email_owner = _resolve_sso_account(
        provider, username, email, external_data)

    if not user and conflict:
        return _refuse_username_conflict(provider, username, conflict)

    if user and not user.active:
        # A disabled account is a refused login: every caller checks it a
        # few lines on. Synchronising first bound the stable identity, which
        # decides whose account this is, for good.
        logger.warning(
            f"SSO sync skipped for '{username}': the local account is disabled")
        return user, None

    if not sso_admission(provider, external_data):
        return _refuse_unmapped(provider, username, external_data, group_source)

    if user:
        if row is None:
            # An SSO account from before migration 024: the first provider to open it records itself.
            row = UserSSOIdentity(provider_id=provider.id)
            user.sso_identities.append(row)
        elif row.provider_id is None:
            row.provider_id, row.orphan_of = provider.id, None  # taken back by the same IdP

        # Bind the stable id (trust-on-first-use) for future stable matching.
        if rebind:
            logger.info(f"SSO external id of '{user.username}' moves from its DN to the LDAP uid")
            row.bind(external_id)
        else:
            _bind_external_id(row, provider, external_id)

        # ── Userinfo sync (email, full name) ─────────────────────────────
        # Controlled by `auto_update_users`. Does NOT touch the role.
        if provider.auto_update_users:
            # SSO identity is the stable external id, not the email, so syncing
            # the directory email is safe even if a local account shares it
            # (email is unique only among local accounts).
            if email and email != user.email:
                user.email = email
            if fullname:
                user.full_name = fullname

        # ── Role sync ────────────────────────────────────────────────────
        role_change = None
        # See #81. Default behaviour: role is set at creation only and
        # then managed in the UCM UI. Re-sync on login is opt-in via
        # `sync_role_on_login` and only acts on an explicit role_mapping
        # match — never falls back to `default_role` for existing users.
        custom_change = None
        if provider.sync_role_on_login:
            mapped_role, mapped_custom = _resolve_mapped_roles(provider, external_data)
            if mapped_role is not None and user.role != mapped_role:
                logger.info(
                    f"SSO role sync: user {username} role changed "
                    f"{user.role} → {mapped_role} (mapping match)"
                )
                role_change = (user.role, mapped_role)
                user.role = mapped_role
            # A custom role set by hand (source NULL) is never replaced nor removed.
            current = user.custom_role.name if user.custom_role_id and user.custom_role else None
            by_hand = user.custom_role_id is not None and user.custom_role_source != 'sso'
            if mapped_custom is not None and not by_hand:
                if user.custom_role_id != mapped_custom.id:
                    custom_change = (current, mapped_custom.name)
                    user.custom_role_id = mapped_custom.id
                user.custom_role_source = 'sso'
            elif user.custom_role_source == 'sso':
                if user.custom_role_id is not None:
                    custom_change = (current, None)
                user.custom_role_id = None
                user.custom_role_source = None

        user.last_login = utc_now()
        try:
            db.session.commit()
        except Exception as e:
            db.session.rollback()
            logger.error(f"Failed to update SSO user {username}: {e}")
            role_change = custom_change = None

        if role_change:
            # Recorded once the new role is committed, and from the values
            # captured before it was assigned. Written first, this call said
            # the role had changed before it had, and its own rollback could
            # undo the identity binding made a few lines above while the
            # assignment that followed was committed anyway.
            from services.audit_service import AuditService
            AuditService.log_action(
                action='role_change',
                resource_type='user',
                resource_name=username,
                username=username,
                details=(
                    f"SSO role sync: role changed from {role_change[0]} to "
                    f"{role_change[1]} (role_mapping match)"
                ),
                success=True
            )
        if custom_change:
            from services.audit_service import AuditService
            AuditService.log_action(
                action='role_change',
                resource_type='user',
                resource_name=username,
                username=username,
                details=(
                    f"SSO role sync: custom role changed from "
                    f"{custom_change[0] or 'none'} to {custom_change[1] or 'none'} "
                    f"(role_mapping match)"
                ),
                success=True
            )
        return user, None

    # Create new user if auto_create is enabled
    if not provider.auto_create_users:
        logger.warning(f"SSO user {username} not found and auto_create disabled")
        return None, 'auto_create_disabled'
    # Only where an account was about to be created: any earlier refusal keeps its answer.
    if email_owner:
        return _refuse_email_conflict(provider, username, email, email_owner,
                                      _email_unverified(provider, external_data))

    # Auto-create a distinct SSO account. The email may already belong to a LOCAL
    # account — that's fine: SSO identity is the stable external id, never the
    # email, so the two accounts coexist (email is unique only among local
    # accounts). An admin who wants a single account attaches the provider to the
    # existing one instead (POST /api/v2/users/<id>/sso-identities). See #136/#138.
    effective_email = email or f'{username}@sso.local'

    # Creation path keeps the historical fallback to default_role.
    mapped_role, mapped_custom = _resolve_mapped_roles(provider, external_data)
    role = _resolve_role(provider, external_data, mapped=mapped_role)

    user = User(
        username=username,
        email=effective_email,
        full_name=fullname or username,
        role=role,
        active=True,
        last_login=utc_now(),
    )
    user.sso_identities.append(UserSSOIdentity(provider_id=provider.id))
    user.sso_identities[0].bind(external_id)
    if mapped_custom is not None:
        user.custom_role_id = mapped_custom.id
        user.custom_role_source = 'sso'

    # SSO users don't have a password — use sentinel that cannot match any hash
    user.password_hash = SSO_NO_PASSWORD

    db.session.add(user)
    try:
        db.session.commit()
    except Exception as e:
        db.session.rollback()
        logger.error(f"Failed to create SSO user {username}: {e}")
        raise

    logger.info(f"Created SSO user: {username} with role {role}")
    return user, None
