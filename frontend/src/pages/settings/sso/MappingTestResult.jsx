import { useTranslation } from 'react-i18next'
import { Badge } from '../../../components'

const REFUSAL_KEYS = {
  account_disabled: 'sso.testMappingRefusalAccountDisabled',
  groups_unreadable: 'sso.testMappingRefusalGroupsUnreadable',
  group_denied: 'sso.testMappingRefusalGroupDenied',
  unmapped: 'sso.testMappingRefusalUnmapped',
  no_default_role: 'sso.testMappingRefusalNoDefaultRole',
}

/** The LDAP mapping test's verdict: a refused user has no resolved role. */
export default function MappingTestResult({ result }) {
  const { t } = useTranslation()
  if (result.found === false) {
    return <p className="text-status-error">{t('sso.testMappingNotFound')}</p>
  }
  const allowed = result.access_allowed === true
  return (
    <>
      <p><span className="text-text-secondary font-medium">DN:</span> <span className="text-text-tertiary font-mono">{result.user_dn}</span></p>
      <p>
        <span className="text-text-secondary font-medium">{t('sso.testMappingGroups')}:</span>{' '}
        {result.groups_readable === false
          ? <span className="text-status-error">{t('sso.testMappingGroupsUnreadable')}</span>
          : result.groups?.length > 0
            ? result.groups.map(g => <Badge key={g} variant="secondary" size="sm" className="mr-1">{g}</Badge>)
            : <span className="text-text-tertiary italic">{t('sso.testMappingNoGroups')}</span>
        }
      </p>
      <p>
        <span className="text-text-secondary font-medium">{t('sso.testMappingAccess')}:</span>{' '}
        <Badge variant={allowed ? 'success' : 'danger'} size="sm">
          {allowed ? t('sso.testMappingAccessAllowed') : t('sso.testMappingAccessRefused')}
        </Badge>
        {!allowed && REFUSAL_KEYS[result.refusal] && (
          <span className="ml-1 text-text-tertiary">{t(REFUSAL_KEYS[result.refusal])}</span>
        )}
      </p>
      {allowed && (
        <p>
          <span className="text-text-secondary font-medium">{t('sso.testMappingResolvedRole')}:</span>{' '}
          <Badge variant={result.resolved_role === 'admin' ? 'danger' : result.resolved_role === 'operator' ? 'warning' : 'info'} size="sm">
            {result.resolved_role}
          </Badge>
          {result.resolved_custom_role && (
            <Badge variant="secondary" size="sm" className="ml-1">{result.resolved_custom_role}</Badge>
          )}
        </p>
      )}
      <p className="text-text-tertiary">{t('sso.testMappingNotChecked')}</p>
    </>
  )
}
