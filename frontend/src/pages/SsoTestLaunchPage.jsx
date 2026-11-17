/**
 * First page of the sign-in test window, opened with noopener by the provider screen: it says
 * it is ready on the same-origin channel, then goes to the IdP URL the screen sends back.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Card, Logo, LoadingSpinner } from '../components'
import { isWebUrl, openChannel } from './settings/sso/signInTestChannel'

export const LAUNCH_WAIT_MS = 30000

export default function SsoTestLaunchPage() {
  const { t } = useTranslation()
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    const key = window.location.hash.slice(1)
    let timer
    const channel = key ? openChannel((msg) => {
      if (msg.key !== key) return
      if (msg.type === 'go' && isWebUrl(msg.url)) {
        clearTimeout(timer)
        channel.close()
        window.location.replace(msg.url)
      } else if (msg.type === 'abort' || msg.type === 'go') {
        setFailed(true)
      }
    }) : null
    if (!channel) {
      setFailed(true)
      return undefined
    }
    channel.postMessage({ type: 'ready', key })
    timer = setTimeout(() => setFailed(true), LAUNCH_WAIT_MS)
    return () => { clearTimeout(timer); channel.close() }
  }, [])

  return (
    <div className="min-h-screen flex items-center justify-center bg-bg-primary p-4">
      <Card className="w-full max-w-md p-6 space-y-4 text-center">
        <Logo />
        <div role="status" className="space-y-2">
          {!failed && <LoadingSpinner size="sm" className="mx-auto" />}
          <p className="text-sm text-text-secondary">
            {failed ? t('sso.signInTestFailed') : t('sso.signInTestLaunching')}
          </p>
        </div>
      </Card>
    </div>
  )
}
