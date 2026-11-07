import { useTranslation } from 'react-i18next'
import { Warning } from '@phosphor-icons/react'

/** Whether the role mapping has at least one rule (blank editor rows do not count). */
export function hasRoleRules(roleMapping) {
  return Object.entries(roleMapping || {}).some(([k, v]) => k && v)
}

/** Who this provider lets in, as the login decides it. */
export default function ProvisioningNotice({ formData }) {
  const { t } = useTranslation()
  if (hasRoleRules(formData.role_mapping)) {
    return <p className="text-xs text-text-tertiary">{t('sso.provisioningRulesNotice')}</p>
  }
  const role = formData.default_role
  return (
    <div role="status" className="p-3 rounded-lg bg-accent-warning-op10 border border-accent-warning-op30 text-xs status-warning-text flex gap-2">
      <Warning size={16} className="shrink-0 mt-0.5" />
      <span>
        {role
          ? t('sso.provisioningNoRulesNotice', { role: t(`common.${role}`) })
          : t('sso.provisioningNobodyNotice')}
      </span>
    </div>
  )
}
