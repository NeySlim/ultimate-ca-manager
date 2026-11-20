/**
 * Bounds the interface knows, checked before a save leaves the page: a value out of them
 * is marked on its field and nothing is sent. Keys: a setting name, or `syslog.<field>`.
 */
const isPort = (v) => v !== '' && v !== null && v !== undefined && /^\d{1,5}$/.test(String(v).trim())
  && Number(v) >= 1 && Number(v) <= 65535

// key -> { section, applies(draft), problem(value) -> translation key or null }
const CHECKS = {
  smtp_port: { section: 'email', read: (d) => d.settings.smtp_port, problem: (v) => (isPort(v) ? null : 'settings.portOutOfRange') },
  acme_public_port: { section: 'general', read: (d) => d.settings.acme_public_port, problem: (v) => (isPort(v) ? null : 'settings.portOutOfRange') },
  'syslog.port': {
    section: 'audit', read: (d) => d.syslog.port, applies: (d) => Boolean(d.syslog.enabled),
    problem: (v) => (isPort(v) ? null : 'settings.portOutOfRange'),
  },
}

export const fieldSection = (key) => CHECKS[key]?.section

/**
 * Problems of the fields that changed: { key: translation key }. `changed` lists the keys
 * that differ from what was loaded; a value left as loaded is not blocked.
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
