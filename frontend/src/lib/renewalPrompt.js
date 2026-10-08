// Bounds the renew route enforces (backend utils/validity.py)
export const RENEW_MIN_DAYS = 1
export const RENEW_MAX_DAYS = 3650

const DAY_MS = 86400000

export function originalDurationDays(cert) {
  const from = Date.parse(cert?.valid_from)
  const to = Date.parse(cert?.valid_to)
  if (!Number.isFinite(from) || !Number.isFinite(to) || to <= from) return null
  return Math.floor((to - from) / DAY_MS)
}

/**
 * Asks how long the renewed certificate lasts. Resolves to null when the user
 * cancels, {} to keep the original duration (left unchanged, it is not sent so
 * the server keeps it exactly), or { validity_days } for a chosen one. A
 * Microsoft CA sets its own durations, so only a confirmation is asked there.
 */
export async function askRenewal(cert, { showPrompt, showConfirm, showError, t }) {
  if (cert?.source === 'msca') {
    const confirmed = await showConfirm(t('certificates.confirmRenew'), {
      title: t('certificates.renewCertificate'),
      confirmText: t('common.renew'),
      variant: 'primary',
    })
    return confirmed ? {} : null
  }
  const original = originalDurationDays(cert)
  const answer = await showPrompt(t('certificates.renewDaysPrompt'), {
    title: t('certificates.renewCertificate'),
    type: 'number',
    defaultValue: original ? String(original) : '',
    confirmText: t('common.renew'),
  })
  if (answer === null || answer === undefined) return null
  const text = String(answer).trim()
  if (text === '' || (original && text === String(original))) return {}
  const days = /^\d+$/.test(text) ? Number(text) : NaN
  if (!(days >= RENEW_MIN_DAYS && days <= RENEW_MAX_DAYS)) {
    showError(t('certificates.renewDaysInvalid', { min: RENEW_MIN_DAYS, max: RENEW_MAX_DAYS }))
    return null
  }
  return { validity_days: days }
}
