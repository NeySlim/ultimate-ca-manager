/** The typed rows the protocol docks give to Facts: a value or its absence, a copyable chip, a yes or no rule. */
import { CodeValue } from '../../components/atelier'

const missing = (v) => v === null || v === undefined || v === ''

/** A row of Facts: the value, or its absence muted (« — » unless said otherwise). */
export function factRow(label, value, absent = '—', extra = {}) {
  return missing(value) ? { label, absent, ...extra } : { label, value, ...extra }
}

/**
 * A row of Facts whose value is copied whole: kind 'url' (a URL or a path) or 'hex' (a digest, a serial)
 * in the shared chip, no kind for an identifier; its absence muted when there is none.
 */
export function copyRow(label, value, kind, extra = {}) {
  if (missing(value)) return { label, absent: '—', ...extra }
  const name = extra.copyLabel || label
  return kind ? { label, value: String(value), kind, long: kind === 'url', ...extra }
    : { label, value: <CodeValue value={value} label={name} />, ...extra }
}

/** A yes or no rule as the state of its row: a check and Oui, or a muted block sign and Non. */
export const yesNoState = (t, value) => (value ? ['', t('common.yes'), 'check'] : ['muted', t('common.no'), 'block'])
