import { useTranslation } from 'react-i18next'
import { Pill, Props } from '../../../components/atelier'

const REFUSAL_KEYS = {
  account_disabled: 'sso.testMappingRefusalAccountDisabled',
  groups_unreadable: 'sso.testMappingRefusalGroupsUnreadable',
  group_denied: 'sso.testMappingRefusalGroupDenied',
  unmapped: 'sso.testMappingRefusalUnmapped',
  no_default_role: 'sso.testMappingRefusalNoDefaultRole',
}
const ROLE_TONE = { admin: 'bad', operator: 'warn' }

/** The LDAP mapping test's verdict, as the mockup's props: a refused user has no resolved role. */
export default function MappingTestResult({ result }) {
  const { t } = useTranslation()
  if (result.found === false) {
    return <p className="test-result bad" role="status"><span>{t('sso.testMappingNotFound')}</span></p>
  }
  const allowed = result.access_allowed === true
  const groups = result.groups_readable === false
    ? <><span className="bad">{t('sso.testMappingGroupsUnreadable')}</span>{result.groups_error && <> <span className="mono">{result.groups_error}</span></>}</>
    : result.groups?.length > 0
      ? <span className="row-actions">{result.groups.map(g => <span key={g} className="chip">{g}</span>)}</span>
      : <span className="muted">{t('sso.testMappingNoGroups')}</span>
  return (
    <div className="field full" role="status">
      <Props items={[
        ['DN', <span key="dn" className="mono">{result.user_dn}</span>],
        [t('sso.testMappingGroups'), groups],
        [t('sso.testMappingAccess'), <>
          <Pill tone={allowed ? 'good' : 'bad'} label={allowed ? t('sso.testMappingAccessAllowed') : t('sso.testMappingAccessRefused')} />
          {!allowed && REFUSAL_KEYS[result.refusal] && <> <span className="muted">{t(REFUSAL_KEYS[result.refusal])}</span></>}
        </>],
        allowed && [t('sso.testMappingResolvedRole'), <>
          <Pill tone={ROLE_TONE[result.resolved_role] || 'muted'} icon="users" label={result.resolved_role} />
          {result.resolved_custom_role && <> <span className="chip">{result.resolved_custom_role}</span></>}
        </>],
      ]} />
      <small>{t('sso.testMappingNotChecked')}</small>
    </div>
  )
}
