import { useTranslation } from 'react-i18next'
import { Notice } from '../../../components/atelier/Form'

/** Whether the role mapping has at least one rule (blank editor rows do not count). */
export function hasRoleRules(roleMapping) {
  return Object.entries(roleMapping || {}).some(([k, v]) => k && v)
}

/** Who this provider lets in, as the login decides it. */
export default function ProvisioningNotice({ formData }) {
  const { t } = useTranslation()
  if (hasRoleRules(formData.role_mapping)) {
    return <Notice><span>{t('sso.provisioningRulesNotice')}</span>{' '}<span>{t('sso.provisioningRefusalAudited')}</span></Notice>
  }
  const role = formData.default_role
  return (
    <Notice tone="warn" role="status">
      {role ? t('sso.provisioningNoRulesNotice', { role: t(`common.${role}`) }) : t('sso.provisioningNobodyNotice')}
    </Notice>
  )
}
