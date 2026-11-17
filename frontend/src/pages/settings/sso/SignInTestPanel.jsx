import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { SignIn } from '@phosphor-icons/react'
import { Button, LoadingSpinner } from '../../../components'
import { ssoService } from '../../../services'
import SignInTestReport from './SignInTestReport'

export const POLL_MS = 2000
const WINDOW_NAME = 'ucm-sso-sign-in-test'

/**
 * OIDC and SAML "Test sign-in": the IdP opens in a new window and this panel shows what the
 * login would have done once the IdP answered. The test runs on the SAVED provider: unsaved
 * changes are announced first, never sent.
 */
export default function SignInTestPanel({ provider, dirty, formData, handleChange }) {
  const { t } = useTranslation()
  const [phase, setPhase] = useState('idle') // idle | confirm | waiting | done | expired | failed | blocked
  const [report, setReport] = useState(null)
  const timer = useRef(null)
  const alive = useRef(true)

  useEffect(() => () => { alive.current = false; clearTimeout(timer.current) }, [])

  if (!provider?.id) return null

  const poll = (id) => {
    timer.current = setTimeout(async () => {
      try {
        const res = await ssoService.getSignInTest(id)
        if (!alive.current) return
        const data = res?.data || res
        if (data?.state === 'done') {
          setReport(data.report)
          setPhase('done')
          return
        }
        poll(id)
      } catch (err) {
        if (!alive.current) return
        setPhase(err?.status === 404 ? 'expired' : 'failed')
      }
    }, POLL_MS)
  }

  const start = async () => {
    clearTimeout(timer.current)
    setReport(null)
    // Opened on the click itself: a window opened after an await is a blocked pop-up.
    const popup = window.open('', WINDOW_NAME)
    if (!popup) {
      setPhase('blocked')
      return
    }
    try {
      const res = await ssoService.startSignInTest(provider.id)
      const data = res?.data || res
      popup.location.href = data.url
      setPhase('waiting')
      poll(data.id)
    } catch {
      popup?.close()
      setPhase('failed')
    }
  }

  const onClick = () => (dirty && phase !== 'confirm' ? setPhase('confirm') : start())

  return (
    <div className="space-y-2">
      <p className="text-xs text-text-tertiary">{t('sso.signInTestDesc')}</p>
      {phase === 'confirm' && (
        <div role="alert" className="p-2.5 rounded-lg bg-accent-warning-op10 border border-accent-warning-op30 text-xs status-warning-text">
          {t('sso.signInTestUnsaved')}
        </div>
      )}
      <Button type="button" variant="secondary" size="sm" onClick={onClick}
        disabled={phase === 'waiting'} className="gap-1.5">
        {phase === 'waiting' ? <LoadingSpinner size="xs" /> : <SignIn size={14} />}
        {phase === 'confirm' ? t('sso.signInTestRunSaved') : t('sso.signInTest')}
      </Button>
      {phase === 'waiting' && <p role="status" className="text-xs text-text-tertiary">{t('sso.signInTestWaiting')}</p>}
      {phase === 'expired' && <p role="status" className="text-xs text-status-error">{t('sso.signInTestExpired')}</p>}
      {phase === 'failed' && <p role="status" className="text-xs text-status-error">{t('sso.signInTestFailed')}</p>}
      {phase === 'blocked' && <p role="status" className="text-xs text-status-error">{t('sso.signInTestPopupBlocked')}</p>}
      {phase === 'done' && report && (
        <div className="p-2.5 rounded-lg border border-border bg-bg-secondary text-xs">
          <SignInTestReport report={report} formData={formData} handleChange={handleChange} />
        </div>
      )}
    </div>
  )
}
