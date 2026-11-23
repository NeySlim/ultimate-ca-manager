import { useTranslation } from 'react-i18next'
import { Facts, Notice, Pill } from '../../../components/atelier'

// The message the login page shows for each refusal code (LoginPage.jsx).
const LOGIN_ERROR_KEYS = {
  invalid_state: 'auth.ssoInvalidState',
  token_exchange_failed: 'auth.ssoTokenFailed',
  userinfo_failed: 'auth.ssoUserinfoFailed',
  no_username: 'auth.ssoNoUsername',
  user_creation_failed: 'auth.ssoUserCreationFailed',
  auto_create_disabled: 'auth.ssoAutoCreateDisabled',
  callback_error: 'auth.ssoCallbackError',
  account_disabled: 'auth.accountDisabled',
  saml_validation_failed: 'auth.samlValidationFailed',
  saml_login_expired: 'auth.samlLoginExpired',
  sso_username_conflict: 'auth.ssoUsernameConflict',
  sso_unmapped: 'auth.ssoUnmapped',
  sso_no_default_role: 'auth.ssoNoDefaultRole',
  sso_email_conflict: 'auth.ssoEmailConflict',
}

// A SAML candidate reads "Name (FriendlyName)": only the Name is mapped (SAML Core §2.7.3.1).
const attributeName = (candidate) => candidate.replace(/ \([^()]*\)$/, '')
const ROLE_TONE = { admin: 'bad', operator: 'warn' }

/** What the login would have done with the identity the IdP returned to a sign-in test, as the mockup's props. */
export default function SignInTestReport({ report, formData, handleChange }) {
  const { t } = useTranslation()
  const accepted = report.verdict === 'accepted'
  const account = report.account || {}
  const identity = report.identity
  const mapped = formData?.attribute_mapping || {}

  const mapToGroups = (name) => {
    handleChange?.('attribute_mapping', { ...mapped, [name]: 'groups' })
  }

  const accountLine = account.outcome && (
    <>
      {account.outcome === 'open' && t('sso.signInTestAccountOpen', { username: account.username })}
      {account.outcome === 'create' && t('sso.signInTestAccountCreate', { username: account.username })}
      {account.outcome === 'disabled' && t('sso.signInTestAccountDisabled', { username: account.username })}
      {account.outcome === 'refused' && (account.username
        ? t('sso.signInTestAccountRefused', { username: account.username })
        : t('sso.signInTestAccountNone'))}
      {account.binds_identity && <span className="muted"> · {t('sso.signInTestAccountBinds')}</span>}
    </>
  )

  return (
    <div className="field full" role="status">
      <Facts items={[
        {
          label: t('sso.signInTestVerdict'),
          state: accepted ? ['good', t('sso.signInTestAccepted')] : ['bad', t('sso.signInTestRefused')],
          // What the login page would have said, under the verdict
          sub: !accepted && report.code && <>{LOGIN_ERROR_KEYS[report.code] ? t(LOGIN_ERROR_KEYS[report.code]) : null}{' '}<span className="mono">({report.code})</span></>,
        },
        report.reason && { label: t('sso.signInTestReason'), value: report.reason, long: true },
        identity && [t('sso.signInTestIdentity'), <>
          <span className="mono">{identity.username}</span>
          {identity.email && <span className="muted"> · {identity.email}</span>}
          {identity.external_id && (
            <span className="muted"> · {t('sso.signInTestExternalId')} <span className="mono">{identity.external_id}</span></span>
          )}
        </>],
        identity && [t('sso.signInTestGroups'), <>
          {report.groups?.length > 0
            ? <span className="row-actions">{report.groups.map(g => <span key={g} className="chip">{g}</span>)}</span>
            : <span className="muted">{t('sso.signInTestNoGroups')}</span>}
          {report.groups_more > 0 && <span className="muted">{t('sso.signInTestMore', { number: report.groups_more })}</span>}
        </>],
        report.group_source && [t('sso.signInTestGroupSource'), report.group_source],
        accepted && [t('sso.signInTestRole'), <>
          <Pill tone={ROLE_TONE[report.role] || 'muted'} icon="users" label={report.role} />
          {report.custom_role && <> <span className="chip">{report.custom_role}</span></>}
          {report.role_change && (
            <> <span className="muted">{t('sso.signInTestRoleChange', { from: report.role_change[0], to: report.role_change[1] })}</span></>
          )}
        </>],
        accountLine && [t('sso.signInTestAccount'), accountLine],
        report.diagnosis && { label: t('sso.signInTestDiagnosis'), value: report.diagnosis, long: true },
        report.detail && !report.diagnosis && { label: t('sso.signInTestDetail'), value: report.detail, long: true },
      ]} />
      {!accepted && report.candidates?.length > 0 && (
        <>
          <small>{t('sso.signInTestCandidates')}</small>
          <span className="row-actions">
            {report.candidates.map(name => {
              const attribute = attributeName(name)
              return (
                <button key={name} type="button" className="btn" disabled={mapped[attribute] === 'groups' || undefined} onClick={() => mapToGroups(attribute)}>
                  {t('sso.signInTestMapToGroups', { name })}
                </button>
              )
            })}
          </span>
          <small>{t('sso.signInTestMapHint')}</small>
        </>
      )}
      {report.not_verified?.length > 0 && (
        <Notice tone="warn">
          <strong>{t('sso.signInTestNotVerified')}</strong>{' '}{report.not_verified.join(' · ')}
        </Notice>
      )}
      {report.provider_enabled === false && <small>{t('sso.signInTestProviderDisabled')}</small>}
      <small>{t('sso.signInTestNothingDone')}</small>
    </div>
  )
}
