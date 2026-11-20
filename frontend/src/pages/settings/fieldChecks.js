/**
 * Bounds the interface knows, checked before a save leaves the page: a value out of them
 * is marked on its field and nothing is sent. Keys: a setting name, or `<part>.<field>`
 * for a part saved by its own route (syslog, auto-renewal).
 */
const text = (v) => (v === null || v === undefined ? '' : String(v)).trim()
const isInt = (v) => /^\d+$/.test(text(v))

// A whole number from min to max; `unit` names the message (minutes, hours, days...)
const range = (min, max, unit = 'count') => ({
  min, max,
  problem: (v) => (isInt(v) && Number(v) >= min && (max === undefined || Number(v) <= max)
    ? null
    : { key: max === undefined ? 'settings.check.atLeast' : `settings.check.range_${unit}`, values: { min, max } }),
})
const port = { min: 1, max: 65535, problem: (v) => (isInt(v) && Number(v) >= 1 && Number(v) <= 65535 ? null : { key: 'settings.portOutOfRange' }) }
// A host name or an IP address, as the mockup checks a server
const HOST = /^(?=.{1,253}$)(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)(?:\.[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?)*$/i
const IPV6 = /^[0-9a-f:]+$/i
const host = { problem: (v) => (HOST.test(text(v)) || (text(v).includes(':') && IPV6.test(text(v))) ? null : { key: 'settings.check.host' }) }
const required = (inner) => ({ problem: (v) => (text(v) ? inner?.problem(v) ?? null : { key: 'settings.check.required' }) })
// Optional fields: an empty value is allowed, a typed one must be well formed
const email = { problem: (v) => (!text(v) || /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(text(v)) ? null : { key: 'settings.check.email' }) }
const url = {
  problem: (v) => {
    if (!text(v)) return null
    try {
      const u = new URL(text(v))
      return ['http:', 'https:'].includes(u.protocol) && u.hostname && !/\s/.test(text(v)) ? null : { key: 'settings.check.url' }
    } catch {
      return { key: 'settings.check.url' }
    }
  },
}
const minutes = (seconds) => (seconds === '' || seconds === null || seconds === undefined || Number.isNaN(seconds) ? '' : Math.round(seconds / 60))
const hours = (seconds) => (seconds === '' || seconds === null || seconds === undefined || Number.isNaN(seconds) ? '' : Math.round(seconds / 3600))

// key -> { section, read(draft) as the field shows it, applies(draft), and the check }
const CHECKS = {
  // Général
  base_url: { section: 'general', read: (d) => d.settings.base_url, ...url },
  protocol_base_url: { section: 'general', read: (d) => d.settings.protocol_base_url, ...url },
  acme_public_port: { section: 'general', read: (d) => d.settings.acme_public_port, ...port },
  session_timeout: { section: 'general', read: (d) => minutes(d.settings.session_timeout), ...range(5, 1440, 'minutes') },
  max_login_attempts: { section: 'general', read: (d) => d.settings.max_login_attempts, ...range(3, 20) },
  lockout_duration: { section: 'general', read: (d) => minutes(d.settings.lockout_duration), ...range(1, 60, 'minutes') },
  // Sécurité
  session_max_lifetime: { section: 'security', read: (d) => hours(d.settings.session_max_lifetime), ...range(1, 720, 'hours') },
  min_password_length: { section: 'security', read: (d) => d.settings.min_password_length, ...range(6, 32) },
  hsts_max_age: { section: 'security', read: (d) => d.settings.hsts_max_age, ...range(0, undefined) },
  ocsp_response_validity_hours: { section: 'security', read: (d) => d.settings.ocsp_response_validity_hours, ...range(1, 168, 'hours') },
  ocsp_responder_renew_days: { section: 'security', read: (d) => d.settings.ocsp_responder_renew_days, ...range(1, 365, 'days') },
  // Sauvegarde
  backup_retention_days: { section: 'backup', read: (d) => d.settings.backup_retention_days, ...range(1, 3650, 'days') },
  backup_max_total_mb: { section: 'backup', read: (d) => d.settings.backup_max_total_mb, ...range(0, 1048576) },
  // Audit: 0 keeps everything, else 7 to 1825 days
  audit_retention_days: {
    section: 'audit', read: (d) => d.settings.audit_retention_days, min: 0, max: 1825,
    problem: (v) => (isInt(v) && (Number(v) === 0 || (Number(v) >= 7 && Number(v) <= 1825)) ? null : { key: 'settings.check.retention' }),
  },
  // SMTP
  smtp_port: { section: 'email', read: (d) => d.settings.smtp_port, ...port },
  smtp_from_email: { section: 'email', read: (d) => d.settings.smtp_from_email, ...email },
  // Syslog: only while it is on, as the mockup checks a field whose box is ticked
  'syslog.host': { section: 'audit', read: (d) => d.syslog.host, applies: (d) => Boolean(d.syslog?.enabled), ...required(host) },
  'syslog.port': { section: 'audit', read: (d) => d.syslog.port, applies: (d) => Boolean(d.syslog?.enabled), ...port },
  // Renouvellement automatique
  'ar.days_before_expiry': { section: 'autoRenewal', read: (d) => d.ar?.days_before_expiry, ...range(1, 365, 'days') },
}

export const fieldSection = (key) => CHECKS[key]?.section

/** The bounds of a field for its input (`min`, `max`), from the same table as the check. */
export const fieldBounds = (key) => {
  const { min, max } = CHECKS[key] || {}
  return { ...(min !== undefined && { min }), ...(max !== undefined && { max }) }
}

/**
 * Problems of the fields that changed: { key: { key, values } } to translate. `changed`
 * lists the keys that differ from what was loaded; a value left as loaded is not blocked.
 */
export function fieldProblems(draft, changed) {
  const out = {}
  for (const key of changed) {
    const check = CHECKS[key]
    if (!check || (check.applies && !check.applies(draft))) continue
    const problem = check.problem(check.read(draft))
    if (problem) out[key] = problem
  }
  return out
}
