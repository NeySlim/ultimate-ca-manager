from . import bp, VALID_ROLES, logger
from .connection_tests import _ldap_authenticate_user
from flask import request, session
from auth.unified import require_auth
from utils.response import success_response, error_response
from utils.db_transaction import safe_commit
from models import db, User
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
from .helpers import _check_ldap_lockout, _clear_ldap_failed_attempts, _record_ldap_failed_attempt, _resolve_mapped_roles, _resolve_role, _build_ldap_tls, _decrypt_ldap_password, sso_admission, _mapping_rules

@bp.route('/api/v2/sso/ldap/login', methods=['POST'])
@limiter.limit("5/minute")
def ldap_login():
    """
    Direct LDAP authentication.
    Unlike OAuth2/SAML, LDAP authenticates with username/password directly.

    On refusals this door says more than the password door, on purpose. Every
    message below that names a reason — the account disabled in the directory,
    the account disabled locally, membership of a required group — is returned
    only after ``_ldap_authenticate_user`` has bound as the user with the
    password supplied, so the caller has already proved it. Before that point
    the answers match the password door's exactly: "Invalid credentials", 401,
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

    # Check account lockout before attempting LDAP auth
    if _check_ldap_lockout(username):
        return error_response("Account temporarily locked due to too many failed attempts", 429)

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

    # Authenticate via LDAP
    user_info, error = _ldap_authenticate_user(provider, username, password)

    if error:
        if error == 'account_disabled':
            # Account exists but is disabled in LDAP — don't count as
            # failed login attempt (not a wrong password).
            AuditService.log_action(
                action='login_failure',
                resource_type='user',
                details=f'LDAP account disabled for {username}',
                success=False,
                username=username
            )
            return error_response("This account has been disabled in Active Directory / LDAP", 403)

        if error == 'group_denied':
            # Authenticated but not in required groups — don't count as
            # failed login attempt.
            AuditService.log_action(
                action='login_failure',
                resource_type='user',
                details=f'LDAP login denied: not in required groups for {username}',
                success=False,
                username=username
            )
            return error_response("Access denied: you are not a member of the required group(s)", 403)

        # Generic auth failure (wrong password, etc.)
        _record_ldap_failed_attempt(username)
        AuditService.log_action(
            action='login_failure',
            resource_type='user',
            details=f'LDAP authentication failed for {username}',
            success=False,
            username=username
        )
        return error_response("Invalid credentials", 401)

    # Create or update user
    user, error_code = _get_or_create_sso_user(
        provider,
        user_info['username'],
        user_info.get('email', ''),
        user_info.get('fullname', ''),
        user_info
    )

    if not user:
        # The password is proved by now, so the refusal may say why.
        if error_code == USERNAME_CONFLICT:
            return error_response(
                "Sign-in refused: a local account, or one linked to another identity, "
                "already uses this name. An administrator can link the accounts.", 403)
        if error_code == UNMAPPED:
            if not _mapping_rules(provider):
                return error_response(
                    "Access denied: this provider has no default role and no role mapping rule", 403)
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

    # Clear failed attempts on successful login
    _clear_ldap_failed_attempts(username)

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
        session.clear()
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

    # Establish Flask session (clear first to prevent session fixation)
    _ldap_now = utc_now()
    session.clear()
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
    from onelogin.saml2.auth import OneLogin_Saml2_Auth

    base = saml_sp.sp_base_url(flask_request)
    sp_cert = sp_key = None
    if sign_request and provider.saml_sign_requests:
        sp_cert, sp_key = saml_sp.load_sp_credentials(provider, with_key=True)
    return OneLogin_Saml2_Auth(saml_sp.request_data(flask_request, base),
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


def _bind_external_id(user, provider, external_id):
    """Bind the stable id to the account (TOFU). Never replaces an id already
    bound, nor takes one another account of this provider owns. True if bound."""
    if not external_id or user.sso_external_id == external_id:
        return True
    if user.sso_external_id:
        logger.warning(
            f"SSO external id of '{user.username}' is already bound; not replacing it")
        return False
    taken = User.query.filter(
        User.sso_provider_id == provider.id,
        User.sso_external_id == external_id,
        User.id != user.id,
    ).first()
    if taken:
        logger.warning(
            f"SSO external id {external_id!r} already bound to '{taken.username}'; "
            f"not rebinding to '{user.username}'")
        return False
    user.sso_external_id = external_id
    return True


SSO_NO_PASSWORD = '!SSO_NO_PASSWORD!'
USERNAME_CONFLICT = 'sso_username_conflict'
UNMAPPED = 'sso_unmapped'


def _adoptable(user, provider):
    """Whether an identity whose stable id matches nobody may claim ``user``:
    an account of this provider (provisioned, or linked by an admin) not bound yet.
    A local account, or one bound to another identity, is never claimed (OIDC Core §5.7)."""
    if user.sso_external_id:
        return False
    if (user.auth_source or 'local') == 'local':
        # SSO account from before migration 024 (which may have set its provider),
        # never converted back by an admin (unlink forces a password change).
        return (user.password_hash == SSO_NO_PASSWORD and not user.force_password_change
                and _same_provider_or_idp(user, provider, legacy=True))
    return user.auth_source == provider.provider_type and _same_provider_or_idp(user, provider)


def _same_provider_or_idp(user, provider, legacy=False):
    """Linked to this provider, or orphaned by a deleted provider for this same IdP.
    An account with no recorded IdP is claimable only if it predates migration 024."""
    if user.sso_provider_id is not None:
        return user.sso_provider_id == provider.id
    if user.sso_orphan_of is None:
        return legacy
    return user.sso_orphan_of == provider.idp_key()


def _orphan_with_id(provider, external_id):
    """The one account bound to ``external_id`` whose deleted provider served this
    same IdP; None when there is none, or several (a stable id is per IdP)."""
    key = provider.idp_key()
    if not key:
        return None
    orphans = User.query.filter(
        User.sso_external_id == external_id,
        User.auth_source == provider.provider_type,
        User.sso_provider_id.is_(None),
        User.sso_orphan_of == key).limit(2).all()
    return orphans[0] if len(orphans) == 1 else None


def _bound_by_dn(provider, external_data, external_id):
    """An LDAP account of this provider bound by its DN fallback, now that the
    directory returns a stable uid for the DN the user bind just proved."""
    from sqlalchemy import func
    dn = str((external_data or {}).get('dn') or '').strip()
    if provider.provider_type != 'ldap' or not dn or dn == external_id:
        return None
    return User.query.filter(User.sso_provider_id == provider.id,
                             func.lower(User.sso_external_id) == dn.lower()).first()


def _email_unverified(provider, external_data):
    """The OIDC IdP says the e-mail is not verified (some send the claim as a string)."""
    if provider.provider_type != 'oauth2':
        return False
    flag = (external_data or {}).get('email_verified')
    return flag is False or (isinstance(flag, str) and flag.strip().lower() == 'false')


def _refuse_username_conflict(provider, username):
    logger.warning(
        f"SSO login refused for '{username}' via {provider.name}: the name belongs to a "
        f"local account or to one bound to another identity")
    AuditService.log_action(
        action='login_failure',
        resource_type='sso',
        resource_name=username,
        details=(f"SSO login via {provider.name} refused: the name {username!r} belongs to a "
                 f"local account or to one bound to another identity (link it with Link to SSO)"),
        success=False,
        username=username,
    )
    return None, USERNAME_CONFLICT


def _refuse_unmapped(provider, username):
    reason = 'no role mapping rule matches it' if _mapping_rules(provider) else 'the provider has no default role'
    logger.warning(f"SSO login refused for '{username}' via {provider.name}: {reason}")
    AuditService.log_action(
        action='login_failure',
        resource_type='sso',
        resource_name=username,
        details=f"SSO login via {provider.name} refused for {username!r}: {reason}",
        success=False,
        username=username,
    )
    return None, UNMAPPED


def _get_or_create_sso_user(provider, username, email, fullname, external_data):
    """Create or update a user from SSO authentication

    Returns:
        tuple: (user, error_code) - user object or None, and error code if failed
    """
    from sqlalchemy import func
    external_id = _extract_external_id(provider, external_data)

    # 1. Stable-identifier match — robust to username/email changes (primary).
    user = None
    rebind = False
    if external_id:
        user = User.query.filter_by(
            sso_provider_id=provider.id, sso_external_id=external_id).first()
        if not user:
            user = _bound_by_dn(provider, external_data, external_id)
            rebind = user is not None
        if not user:
            user = _orphan_with_id(provider, external_id)

    # 2. Not bound yet (legacy, or linked by an admin): match by username, but
    #    only an account this identity may claim.
    conflict = False
    if not user:
        user = User.query.filter_by(username=username).first()
        if user and not _adoptable(user, provider):
            conflict, user = True, None

    # 3. An account an admin linked to this provider that owns this email but
    #    whose username differs (#138). Never a local or already bound account,
    #    nor by an e-mail the OIDC IdP says is unverified.
    if not user and email and not _email_unverified(provider, external_data):
        norm = email.strip().lower()
        candidates = User.query.filter(func.lower(User.email) == norm).all()
        user = next((u for u in candidates
                     if (u.auth_source or 'local') != 'local' and _adoptable(u, provider)), None)

    if not user and conflict:
        return _refuse_username_conflict(provider, username)

    if user and not user.active:
        # A disabled account is a refused login: every caller checks it a
        # few lines on. Synchronising first bound `sso_external_id`, which
        # decides whose account this is, for good.
        logger.warning(
            f"SSO sync skipped for '{username}': the local account is disabled")
        return user, None

    if not sso_admission(provider, external_data):
        return _refuse_unmapped(provider, username)

    if user:
        # Backfill auth_source/sso_provider_id for users created before
        # migration 024 — useful when several providers share a directory
        # and the migration could not infer the right one.
        if (user.auth_source or 'local') == 'local' and user.password_hash == SSO_NO_PASSWORD:
            user.auth_source = provider.provider_type
            user.sso_provider_id = provider.id
        elif user.sso_provider_id != provider.id:
            user.sso_provider_id = provider.id  # unlinked, or its provider was deleted
        user.sso_orphan_of = None

        # Bind the stable id (trust-on-first-use) for future stable matching.
        if rebind:
            logger.info(f"SSO external id of '{user.username}' moves from its DN to the LDAP uid")
            user.sso_external_id = external_id
        else:
            _bind_external_id(user, provider, external_id)

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

    # Auto-create a distinct SSO account. The email may already belong to a LOCAL
    # account — that's fine: SSO identity is the stable external id, never the
    # email, so the two accounts coexist (email is unique only among local
    # accounts). An admin who wants a single merged account links them instead
    # (POST /api/v2/users/<id>/link-sso). See #136/#138.
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
        auth_source=provider.provider_type,
        sso_provider_id=provider.id,
        sso_external_id=external_id,
    )
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
