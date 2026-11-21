/**
 * ForceEnroll2FA Component — mandatory 2FA enrolment overlay (#141)
 *
 * Shown after login whenever the session is flagged `must_enroll_2fa`
 * (local accounts under global enforcement, or SSO accounts whose provider
 * enforces 2FA). A confirmed TOTP app or a registered security key lifts it.
 * Cannot be dismissed: the only escape is to log out. Survives
 * reloads because AuthContext.checkSession re-reads the flag from /auth/verify.
 * Drawn in the mockup's authPage() card, the step that follows the sign-in.
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { useAuth, useNotification } from '../contexts'
import { accountService } from '../services'
import { AuthFrame, AuthField } from './auth/AuthFrame'
import { Icon } from './atelier/Icon'

export function ForceEnroll2FA({ onComplete }) {
  const { t } = useTranslation()
  const { logout } = useAuth()
  const { showError, showSuccess } = useNotification()
  const [qrData, setQrData] = useState(null)
  const [code, setCode] = useState('')
  const [backupCodes, setBackupCodes] = useState(null)
  const [loading, setLoading] = useState(false)
  const [keyName, setKeyName] = useState('')
  const [registeringKey, setRegisteringKey] = useState(false)
  const [closedSessions, setClosedSessions] = useState(undefined)
  // The other sessions are mentioned unless the server reports it closed none
  const enrolled = (key, closed) => showSuccess(closed === 0
    ? t(key) : `${t(key)} ${t('account.otherSessionsClosed')}`)
  const keySupported = typeof window !== 'undefined' && window.PublicKeyCredential !== undefined

  // Kick off enrolment on mount: fetch the TOTP secret + QR.
  useEffect(() => {
    let cancelled = false
    accountService.enable2FA()
      .then((res) => { if (!cancelled) setQrData(res.data || res) })
      .catch((e) => showError(e.message || t('account.twoFaSetupFailed')))
    return () => { cancelled = true }
  }, [])

  const handleVerify = async () => {
    setLoading(true)
    try {
      const res = await accountService.confirm2FA(code)
      const data = res.data || res
      // Backup codes are returned once — force the user to acknowledge them
      // before the session is promoted.
      setClosedSessions(res?.meta?.other_sessions_closed)
      setBackupCodes(data.backup_codes || [])
    } catch (error) {
      showError(error.message || t('auth.invalidTotpCode'))
      setCode('')
    } finally {
      setLoading(false)
    }
  }

  // A registered security key satisfies the requirement too: the backend lifts the gate.
  const handleRegisterKey = async () => {
    setRegisteringKey(true)
    try {
      const res = await accountService.registerWebAuthnKey(keyName.trim() || t('account.securityKey'))
      enrolled('account.keyRegistered', res?.meta?.other_sessions_closed)
      await onComplete?.()
    } catch (error) {
      showError(error.name === 'NotAllowedError'
        ? t('account.registrationCancelled')
        : (error.message || t('account.registrationFailed')))
    } finally {
      setRegisteringKey(false)
    }
  }

  const handleDone = async () => {
    enrolled('account.twoFaEnabled', closedSessions)
    // Re-check the session: the backend has lifted the enrolment gate, so this
    // promotes the session to full access and clears must_enroll_2fa.
    await onComplete?.()
  }

  const verify = (e) => {
    e.preventDefault()
    if (!loading && code.length === 6) handleVerify()
  }

  return (
    <AuthFrame title={t('account.enroll2faRequired')} lead={t('account.enroll2faReason')}>
      {!backupCodes && qrData && (
        <>
          <p className="auth-lead">{t('account.scanQRCode')}</p>
          <div className="auth-qr"><img src={qrData.qr_code} alt={t('account.qrCodeAlt')} width="176" height="176" /></div>
          <form className="auth-form" id="enroll-form" onSubmit={verify} noValidate aria-busy={loading || undefined}>
            <AuthField id="enroll-code" label={t('account.enterDigitCode')}>
              <input
                id="enroll-code"
                name="code"
                inputMode="numeric"
                autoComplete="one-time-code"
                placeholder={t('account.codePlaceholder')}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                maxLength={6}
              />
            </AuthField>
            <button type="submit" className="btn primary auth-submit" disabled={loading || code.length !== 6}>
              <Icon name="check" />{loading ? t('common.loading') : t('account.verifyAndEnable')}
            </button>
          </form>
        </>
      )}

      {!backupCodes && keySupported && (
        <>
          {qrData && <p className="auth-sep"><span>{t('auth.page.or')}</span></p>}
          <AuthField id="enroll-key-name" label={t('account.keyName')}>
            <input
              id="enroll-key-name"
              placeholder={t('account.keyNamePlaceholder')}
              value={keyName}
              onChange={(e) => setKeyName(e.target.value)}
              disabled={registeringKey}
            />
          </AuthField>
          <button type="button" className="btn auth-alt" id="enroll-key" onClick={handleRegisterKey} disabled={registeringKey}>
            <Icon name="chip" />
            <span>{registeringKey ? t('account.waitingForKey') : t('account.registerKey')}<small>{t('account.enroll2faOrKey')}</small></span>
          </button>
        </>
      )}

      {backupCodes && (
        <>
          <div className="notice warn" role="status">
            <Icon name="warning" />
            <span><strong>{t('account.backupCodes')}</strong> {t('account.backupCodesHint')}</span>
          </div>
          <ul className="backup-codes mono">
            {backupCodes.map((c, i) => <li key={i}>{c}</li>)}
          </ul>
          <button type="button" className="btn primary auth-submit" onClick={handleDone}>
            <Icon name="check" />{t('account.backupCodesSaved')}
          </button>
        </>
      )}

      <button type="button" className="text-link auth-switch" onClick={logout}>{t('common.logout')}</button>
    </AuthFrame>
  )
}

export default ForceEnroll2FA
