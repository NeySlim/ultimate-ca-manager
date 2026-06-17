/**
 * ForceEnroll2FA Component — mandatory 2FA enrolment overlay (#141)
 *
 * Shown after login whenever the session is flagged `must_enroll_2fa`
 * (local accounts under global enforcement, or SSO accounts whose provider
 * enforces 2FA). Cannot be dismissed: the only escape is to log out. Survives
 * reloads because AuthContext.checkSession re-reads the flag from /auth/verify.
 */
import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { ShieldCheck, Warning, SignOut } from '@phosphor-icons/react'
import { Modal, Button, Input } from '../components'
import { useAuth, useNotification } from '../contexts'
import { accountService } from '../services'

export function ForceEnroll2FA({ onComplete }) {
  const { t } = useTranslation()
  const { logout } = useAuth()
  const { showError, showSuccess } = useNotification()
  const [qrData, setQrData] = useState(null)
  const [code, setCode] = useState('')
  const [backupCodes, setBackupCodes] = useState(null)
  const [loading, setLoading] = useState(false)

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
      setBackupCodes(data.backup_codes || [])
    } catch (error) {
      showError(error.message || t('auth.invalidTotpCode'))
      setCode('')
    } finally {
      setLoading(false)
    }
  }

  const handleDone = async () => {
    showSuccess(t('account.twoFaEnabled'))
    // Re-check the session: the backend has lifted the enrolment gate, so this
    // promotes the session to full access and clears must_enroll_2fa.
    await onComplete?.()
  }

  return (
    <Modal open={true} onClose={() => {}} title={t('account.enroll2faRequired')}>
      <div className="p-4 space-y-4">
        <div className="flex items-start gap-3 p-3 rounded-lg bg-accent-warning-op10 border border-accent-warning-op30">
          <Warning size={20} className="text-accent-warning flex-shrink-0 mt-0.5" />
          <div className="text-sm">
            <p className="font-medium text-accent-warning">{t('account.enroll2faRequired')}</p>
            <p className="text-text-secondary mt-1">{t('account.enroll2faReason')}</p>
          </div>
        </div>

        {!backupCodes && qrData && (
          <>
            <div>
              <p className="text-sm text-text-secondary mb-3">{t('account.scanQRCode')}</p>
              <div className="flex justify-center p-4 bg-white rounded-lg">
                <img src={qrData.qr_code} alt="2FA QR Code" className="w-48 h-48" />
              </div>
            </div>
            <div>
              <p className="text-sm text-text-secondary mb-2">{t('account.enterDigitCode')}</p>
              <Input
                type="text"
                placeholder={t('account.codePlaceholder')}
                value={code}
                onChange={(e) => setCode(e.target.value.replace(/\D/g, '').slice(0, 6))}
                maxLength={6}
                className="text-center text-2xl tracking-widest font-mono"
              />
            </div>
          </>
        )}

        {backupCodes && (
          <div className="p-3 bg-status-warning-op10 border border-status-warning-op30 rounded-lg">
            <p className="text-sm font-medium text-status-warning flex items-center gap-2">
              <Warning size={16} />
              {t('account.backupCodes')}
            </p>
            <p className="text-xs text-text-secondary mt-1">{t('account.backupCodesHint')}</p>
            <div className="mt-2 grid grid-cols-2 gap-1 font-mono text-xs">
              {backupCodes.map((c, i) => (
                <span key={i} className="text-text-secondary">{c}</span>
              ))}
            </div>
          </div>
        )}

        <div className="flex justify-between pt-2 border-t border-border">
          <Button variant="ghost" onClick={logout} type="button">
            <SignOut size={16} />
            {t('common.logout')}
          </Button>
          {backupCodes ? (
            <Button type="button" onClick={handleDone}>
              <ShieldCheck size={16} />
              {t('account.backupCodesSaved')}
            </Button>
          ) : (
            <Button type="button" onClick={handleVerify} disabled={loading || code.length !== 6}>
              <ShieldCheck size={16} />
              {loading ? t('common.loading') : t('account.verifyAndEnable')}
            </Button>
          )}
        </div>
      </div>
    </Modal>
  )
}

export default ForceEnroll2FA
