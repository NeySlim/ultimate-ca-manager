import { useEffect, useRef, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { Btn, Icon } from '../../../components/atelier'
import { Notice } from '../../../components/atelier/Form'
import { ssoService } from '../../../services'
import SignInTestReport from './SignInTestReport'
import { LAUNCH_PATH, openChannel, randomKey } from './signInTestChannel'

export const POLL_MS = 2000
// How long the new window has to say it is ready before the browser is deemed to have blocked it
export const LAUNCH_MS = 15000
const OPEN_FEATURES = 'noopener,noreferrer'

/**
 * OIDC and SAML "Test sign-in": the IdP opens in a new window and this panel shows what the
 * login would have done once the IdP answered. The test runs on the SAVED provider: unsaved
 * changes are announced first, never sent.
 */
export default function SignInTestPanel({ provider, dirty, formData, handleChange }) {
  const { t } = useTranslation()
  const [phase, setPhase] = useState('idle') // idle | confirm | opening | waiting | done | expired | failed | blocked
  const [report, setReport] = useState(null)
  const alive = useRef(true)
  // One test at a time: its channel, the key the launch window answers with, its timers.
  const run = useRef(null)

  const stop = () => {
    const r = run.current
    run.current = null
    if (!r) return
    clearTimeout(r.timer)
    clearTimeout(r.launchTimer)
    r.channel?.close()
  }

  // Drops the test in progress: a window still opening is told to stop, the wait ends here.
  const abandon = () => {
    const r = run.current
    if (r && !r.id) r.channel?.postMessage({ type: 'abort', key: r.key })
    stop()
  }

  // Set on every mount: StrictMode unmounts and mounts again before the first click.
  useEffect(() => {
    alive.current = true
    return () => { alive.current = false; stop() }
  }, [])

  if (!provider?.id) return null

  const poll = (r, delay) => {
    clearTimeout(r.timer)
    r.timer = setTimeout(async () => {
      try {
        const res = await ssoService.getSignInTest(r.id)
        if (!alive.current || run.current !== r) return
        const data = res?.data || res
        if (data?.state === 'done') {
          stop()
          setReport(data.report)
          setPhase('done')
          return
        }
        poll(r, POLL_MS)
      } catch (err) {
        if (!alive.current || run.current !== r) return
        stop()
        setPhase(err?.status === 404 ? 'expired' : 'failed')
      }
    }, delay)
  }

  // The test window is ready: start the test, then hand it the IdP URL to go to.
  const begin = async (r) => {
    try {
      const res = await ssoService.startSignInTest(provider.id)
      const data = res?.data || res
      if (!alive.current || run.current !== r) {
        r.channel?.postMessage({ type: 'abort', key: r.key })
        return
      }
      r.id = data.id
      if (r.channel) r.channel.postMessage({ type: 'go', key: r.key, url: data.url })
      else window.open(data.url, '_blank', OPEN_FEATURES)
      setPhase('waiting')
      poll(r, POLL_MS)
    } catch {
      r.channel?.postMessage({ type: 'abort', key: r.key })
      if (!alive.current || run.current !== r) return
      stop()
      setPhase('failed')
    }
  }

  const start = () => {
    abandon()
    setReport(null)
    const r = { key: randomKey(), started: false }
    r.channel = openChannel((msg) => {
      if (run.current !== r) return
      if (msg.type === 'ready' && msg.key === r.key && !r.started) {
        r.started = true
        clearTimeout(r.launchTimer)
        begin(r)
      } else if (msg.type === 'complete' && r.id) {
        poll(r, 0) // the test window says the IdP answered: read the report now
      }
    })
    run.current = r
    if (!r.channel) {
      r.started = true
      setPhase('opening')
      begin(r)
      return
    }
    // noopener: the IdP page gets no handle on this screen; the window answers on the channel.
    window.open(`${LAUNCH_PATH}#${r.key}`, '_blank', OPEN_FEATURES)
    setPhase('opening')
    r.launchTimer = setTimeout(() => {
      if (run.current !== r || r.started) return
      stop()
      setPhase('blocked')
    }, LAUNCH_MS)
  }

  const busy = phase === 'opening' || phase === 'waiting'
  const cancel = () => {
    abandon()
    setPhase('idle')
  }

  // Asking for confirmation ends the test in progress, whose poll would otherwise replace it.
  const onClick = () => {
    if (!dirty || phase === 'confirm') return start()
    abandon()
    setPhase('confirm')
  }

  // The mockup's settings test: the button, then the state of the run or the hint at rest
  const failure = { expired: 'sso.signInTestExpired', failed: 'sso.signInTestFailed', blocked: 'sso.signInTestPopupBlocked' }[phase]
  return (
    <>
      {phase === 'confirm' && <Notice tone="warn" role="alert">{t('sso.signInTestUnsaved')}</Notice>}
      <div className="settings-test">
        <Btn icon="arrow" onClick={onClick}>{phase === 'confirm' ? t('sso.signInTestRunSaved') : t('sso.signInTest')}</Btn>
        {busy ? (
          <p className="test-result muted">
            <Icon name="clock" /><span role="status">{t('sso.signInTestWaiting')}</span>{' '}
            <button type="button" className="text-link" onClick={cancel}>{t('sso.signInTestCancel')}</button>
          </p>
        ) : failure ? (
          <p className="test-result bad" role="status"><Icon name="warning" /><span>{t(failure)}</span></p>
        ) : (
          <p className="test-result muted"><Icon name="help" /><span>{t('sso.signInTestDesc')}</span></p>
        )}
      </div>
      {phase === 'done' && report && <SignInTestReport report={report} formData={formData} handleChange={handleChange} />}
    </>
  )
}
