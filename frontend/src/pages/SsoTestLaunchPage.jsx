/**
 * First page of the sign-in test window, opened with noopener by the provider screen: it says
 * it is ready on the same-origin channel, then goes to the IdP URL the screen sends back.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { AuthFrame } from '../components/auth/AuthFrame'
import { Icon } from '../components/atelier/Icon'
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
    <AuthFrame title={t('sso.signInTest')} tools={false} footer={false}>
      {/* The mockup's notice: neutral while the provider opens, warning when it cannot */}
      <p role="status" className={failed ? 'notice warn' : 'notice'}>
        <Icon name={failed ? 'warning' : 'clock'} />
        <span>{failed ? t('sso.signInTestFailed') : t('sso.signInTestLaunching')}</span>
      </p>
    </AuthFrame>
  )
}
