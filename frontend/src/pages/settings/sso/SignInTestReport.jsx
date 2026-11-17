import { useTranslation } from 'react-i18next'
import { Badge, Button } from '../../../components'

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

function Row({ label, children }) {
  return (
    <p>
      <span className="text-text-secondary font-medium">{label}:</span>{' '}
      {children}
    </p>
  )
}

/** What the login would have done with the identity the IdP returned to a sign-in test. */
export default function SignInTestReport({ report, formData, handleChange }) {
  const { t } = useTranslation()
  const accepted = report.verdict === 'accepted'
  const account = report.account || {}
  const identity = report.identity
  // Every other enabled provider of the type: the login takes one of them, in no set order.
  const others = report.other_enabled_providers || []
  const mapped = formData?.attribute_mapping || {}

  const mapToGroups = (name) => {
    handleChange?.('attribute_mapping', { ...mapped, [name]: 'groups' })
  }

  return (
    <div role="status" className="space-y-1">
      <Row label={t('sso.signInTestVerdict')}>
        <Badge variant={accepted ? 'success' : 'danger'} size="sm">
          {accepted ? t('sso.signInTestAccepted') : t('sso.signInTestRefused')}
        </Badge>
        {!accepted && report.code && (
          <span className="ml-1 text-text-tertiary">
            {LOGIN_ERROR_KEYS[report.code] ? t(LOGIN_ERROR_KEYS[report.code]) : null}{' '}
            <span className="font-mono">({report.code})</span>
          </span>
        )}
      </Row>
      {report.reason && <Row label={t('sso.signInTestReason')}>{report.reason}</Row>}
      {identity && (
        <Row label={t('sso.signInTestIdentity')}>
          <span className="font-mono">{identity.username}</span>
          {identity.email && <span className="text-text-tertiary"> · {identity.email}</span>}
          {identity.external_id && (
            <span className="text-text-tertiary"> · {t('sso.signInTestExternalId')} <span className="font-mono">{identity.external_id}</span></span>
          )}
        </Row>
      )}
      {identity && (
        <Row label={t('sso.signInTestGroups')}>
          {report.groups?.length > 0
            ? report.groups.map(g => <Badge key={g} variant="secondary" size="sm" className="mr-1">{g}</Badge>)
            : <span className="text-text-tertiary italic">{t('sso.signInTestNoGroups')}</span>}
          {report.groups_more > 0 && (
            <span className="text-text-tertiary">{t('sso.signInTestMore', { number: report.groups_more })}</span>
          )}
        </Row>
      )}
      {report.group_source && <Row label={t('sso.signInTestGroupSource')}>{report.group_source}</Row>}
      {accepted && (
        <Row label={t('sso.signInTestRole')}>
          <Badge variant={report.role === 'admin' ? 'danger' : report.role === 'operator' ? 'warning' : 'info'} size="sm">
            {report.role}
          </Badge>
          {report.custom_role && <Badge variant="secondary" size="sm" className="ml-1">{report.custom_role}</Badge>}
          {report.role_change && (
            <span className="ml-1 text-text-tertiary">
              {t('sso.signInTestRoleChange', { from: report.role_change[0], to: report.role_change[1] })}
            </span>
          )}
        </Row>
      )}
      {account.outcome && (
        <Row label={t('sso.signInTestAccount')}>
          {account.outcome === 'open' && t('sso.signInTestAccountOpen', { username: account.username })}
          {account.outcome === 'create' && t('sso.signInTestAccountCreate', { username: account.username })}
          {account.outcome === 'disabled' && t('sso.signInTestAccountDisabled', { username: account.username })}
          {account.outcome === 'refused' && (account.username
            ? t('sso.signInTestAccountRefused', { username: account.username })
            : t('sso.signInTestAccountNone'))}
          {account.binds_identity && <span className="text-text-tertiary"> · {t('sso.signInTestAccountBinds')}</span>}
        </Row>
      )}
      {report.diagnosis && <Row label={t('sso.signInTestDiagnosis')}>{report.diagnosis}</Row>}
      {report.detail && !report.diagnosis && <Row label={t('sso.signInTestDetail')}>{report.detail}</Row>}
      {!accepted && report.candidates?.length > 0 && (
        <div>
          <p className="text-text-secondary font-medium">{t('sso.signInTestCandidates')}</p>
          <div className="flex flex-wrap gap-1 mt-1">
            {report.candidates.map(name => {
              const attribute = attributeName(name)
              return (
                <Button key={name} type="button" variant="secondary" size="sm"
                  disabled={mapped[attribute] === 'groups'} onClick={() => mapToGroups(attribute)}>
                  {t('sso.signInTestMapToGroups', { name })}
                </Button>
              )
            })}
          </div>
          <p className="text-text-tertiary mt-1">{t('sso.signInTestMapHint')}</p>
        </div>
      )}
      {report.not_verified?.length > 0 && (
        <div className="status-warning-text">
          <p className="font-medium">{t('sso.signInTestNotVerified')}</p>
          <ul className="list-disc ml-4">
            {report.not_verified.map(item => <li key={item}>{item}</li>)}
          </ul>
        </div>
      )}
      {others.length > 0 && (
        <p role="alert" className="status-warning-text">
          {t(report.provider_enabled === false ? 'sso.signInTestShadowedDisabled' : 'sso.signInTestShadowed',
            { names: others.map(p => p.name).join(', ') })}
        </p>
      )}
      {report.provider_enabled === false && (
        <p className="text-text-tertiary">{t('sso.signInTestProviderDisabled')}</p>
      )}
      <p className="text-text-tertiary">{t('sso.signInTestNothingDone')}</p>
    </div>
  )
}
