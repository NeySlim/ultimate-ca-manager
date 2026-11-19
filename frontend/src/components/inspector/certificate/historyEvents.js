// A record milestone and its audit entry are one event when this close
const SAME_EVENT_MS = 10000
const IMPORTED = ['import', 'imported', 'upload']

/** What the certificate record itself keeps of its life. */
export function recordEvents(cert, t) {
  const events = []
  if (cert.created_at) {
    events.push({
      at: cert.created_at, actor: cert.created_by || '',
      label: t(IMPORTED.includes(cert.source) ? 'inspector.history.imported' : 'inspector.history.issued'),
    })
  }
  if (cert.renewed_at) {
    events.push({
      at: cert.renewed_at, actor: '',
      label: cert.renewed_times > 1 ? t('inspector.history.renewedTimes', { count: cert.renewed_times }) : t('inspector.history.renewed'),
    })
  }
  if (cert.revoked && cert.revoked_at) {
    const reason = cert.revoke_reason ? t(`revocation.reasons.${cert.revoke_reason}`, cert.revoke_reason) : ''
    events.push({
      at: cert.revoked_at, actor: '', revoked: true,
      label: reason ? t('inspector.history.revokedReason', { reason }) : t('inspector.history.revoked'),
    })
  }
  return events
}

/** Audit entries and record milestones in one list, newest first, an event counted once. */
export function mergeHistory(record, audit) {
  const times = audit.map((e) => new Date(e.at).getTime())
  const kept = record.filter((e) => !times.some((ms) => Math.abs(ms - new Date(e.at).getTime()) <= SAME_EVENT_MS))
  return [...audit, ...kept].sort((a, b) => new Date(b.at) - new Date(a.at))
}

/** An audit log row as a history event. */
export const fromAudit = (log) => ({
  at: log.timestamp,
  actor: log.username || '',
  label: String(log.action || '').replace(/[_.]/g, ' '),
  detail: log.details || '',
  failed: log.success === false,
  revoked: /revok/.test(String(log.action || '')),
})
