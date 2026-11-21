import { useTranslation } from 'react-i18next'
import { Section, Props } from '../../components/atelier'
import { YesNo } from '../admin/YesNo'

// The 2FA state the login applies, as the users API reports it.
export default function UserSecuritySection({ user, children }) {
  const { t } = useTranslation()
  return (
    <Section title={t('common.security')}>
      <Props items={[
        [t('common.twoFactorAuth'), <YesNo key="2fa" value={user.two_factor_enabled} />],
        [t('common.totp', 'TOTP'), <YesNo key="totp" value={user.totp_enabled} />],
        [t('users.exempt2faLabel'), <YesNo key="exempt" value={user.totp_exempt} />],
      ]} />
      {children}
    </Section>
  )
}
