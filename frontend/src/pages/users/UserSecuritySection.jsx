import { useTranslation } from 'react-i18next'
import { Section, Facts } from '../../components/atelier'

// The 2FA state the login applies, as the users API reports it: a factor off is neutral, an exemption warns.
export default function UserSecuritySection({ user, children }) {
  const { t } = useTranslation()
  const onOff = (on) => (on ? ['good', t('common.enabled')] : ['muted', t('common.disabled')])
  return (
    <Section title={t('common.security')}>
      <Facts items={[
        { label: t('common.twoFactorAuth'), state: onOff(user.two_factor_enabled) },
        { label: t('common.totp', 'TOTP'), state: onOff(user.totp_enabled) },
        { label: t('users.exempt2faLabel'), state: user.totp_exempt ? ['warn', t('common.yes')] : ['muted', t('common.no')] },
      ]} />
      {children}
    </Section>
  )
}
