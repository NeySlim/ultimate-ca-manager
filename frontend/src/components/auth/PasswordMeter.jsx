/**
 * Strength of a new password, as the server scores it (lib/passwordStrength):
 * five bars and the level in words, never the colour alone.
 */
import { useEffect, useState } from 'react'
import { useTranslation } from 'react-i18next'
import { barsForScore, fetchPasswordStrength, localPasswordStrength } from '../../lib/passwordStrength'

export function PasswordMeter({ password }) {
  const { t } = useTranslation()
  const [result, setResult] = useState(null)

  useEffect(() => {
    if (!password) {
      setResult(null)
      return undefined
    }
    let cancelled = false
    // The offline reading at once, replaced by the server's; the last answer wins
    setResult(previous => previous || localPasswordStrength(password))
    const timer = setTimeout(() => {
      fetchPasswordStrength(password).then(r => { if (!cancelled) setResult(r) })
    }, 300)
    return () => { cancelled = true; clearTimeout(timer) }
  }, [password])

  if (!password || !result) return null
  const level = ['weak', 'fair', 'good', 'strong'].includes(result.level) ? result.level : 'weak'
  const bars = barsForScore(result.score)
  return (
    <div className={`auth-meter is-${level}`}>
      <span className="auth-meter-bars" aria-hidden="true">
        {[0, 1, 2, 3, 4].map(i => <i key={i} className={i < bars ? 'is-on' : undefined} />)}
      </span>
      <span>{t(`passwordStrength.${level}`)}</span>
    </div>
  )
}
