/**
 * Where an SSO sign-in test lands once the IdP answered: it says the test is over and never
 * shows the application, whoever signed in at the IdP. The result is read on the provider screen.
 */
import { useEffect } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { CheckCircle, Warning } from '@phosphor-icons/react'
import { Card, Logo } from '../components'

const RESULTS = {
  done: 'sso.signInTestCompleteDone',
  used: 'sso.signInTestCompleteUsed',
  expired: 'sso.signInTestCompleteExpired',
  other_browser: 'sso.signInTestCompleteOtherBrowser',
}

export default function SsoTestCompletePage() {
  const { t } = useTranslation()
  const [params] = useSearchParams()
  const result = RESULTS[params.get('result')] ? params.get('result') : 'expired'
  const done = result === 'done'

  useEffect(() => {
    // The window the provider screen opened closes itself; one the browser keeps stays readable.
    if (done && window.opener) {
      const timer = setTimeout(() => window.close(), 1500)
      return () => clearTimeout(timer)
    }
    return undefined
  }, [done])

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary p-4">
      <Card className="w-full max-w-md p-6 space-y-4 text-center">
        <Logo />
        <div role="status" className="space-y-2">
          {done
            ? <CheckCircle size={32} className="mx-auto text-status-success" />
            : <Warning size={32} className="mx-auto text-status-warning" />}
          <h1 className="text-lg font-semibold text-text-primary">{t('sso.signInTestCompleteTitle')}</h1>
          <p className="text-sm text-text-secondary">{t(RESULTS[result])}</p>
        </div>
        <Link to="/settings?tab=sso" className="text-sm text-accent-primary hover:underline">
          {t('sso.signInTestCompleteBack')}
        </Link>
      </Card>
    </div>
  )
}
