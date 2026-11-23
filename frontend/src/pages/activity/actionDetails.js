/** English sentences the server writes as an event's detail, shown in the user's language when known. */

const DETAILS = [
  [/^Read SCEP challenge password for CA: (.*)$/s, 'scepChallengeRead'],
  [/^Regenerated SCEP challenge password for CA: (.*)$/s, 'scepChallengeRegenerate'],
]

/** An event's detail in the user's language when the server wrote a known English sentence; else as written. */
export function actionDetail(detail, t) {
  const text = String(detail ?? '')
  for (const [re, key] of DETAILS) {
    const m = t && text.match(re)
    if (m) return t(`audit.actionDetails.${key}`, { name: m[1] })
  }
  return detail
}
