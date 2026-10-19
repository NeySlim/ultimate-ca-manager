import { useTranslation } from 'react-i18next'
import { ShieldCheck } from '@phosphor-icons/react'
import { CompactSection, CompactGrid, CompactField } from '../../components'

// The 2FA state the login applies, as the users API reports it.
export default function UserSecuritySection({ user }) {
  const { t } = useTranslation()
  const yesNo = (value) => (value ? t('common.yes') : t('common.no'))
  return (
    <CompactSection title={t('common.security')} icon={ShieldCheck} iconClass="icon-bg-purple">
      <CompactGrid columns={1}>
        <CompactField autoIcon="enable2FA" label={t('common.twoFactorAuth')} value={yesNo(user.two_factor_enabled)} />
        <CompactField autoIcon="totp" label={t('common.totp', 'TOTP')} value={yesNo(user.totp_enabled)} />
        <CompactField autoIcon="totp" label={t('users.exempt2faLabel')} value={yesNo(user.totp_exempt)} />
      </CompactGrid>
    </CompactSection>
  )
}
