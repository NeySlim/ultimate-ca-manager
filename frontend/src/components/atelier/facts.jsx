/** The rows the docks and settings give to Facts: a value or its absence, a value copied whole, a yes or no rule. */
import { CodeValue } from './Detail'

/** A value Facts has nothing to write for: null, undefined, an empty text, false. Zero is a value. */
export const isMissing = (v) => v === null || v === undefined || v === '' || v === false

/**
 * A row of Facts: the value, with `extra` (long, kind, a key…), or its absence muted, « — » unless `absent`
 * says otherwise; an absence takes none of `extra`, so it never goes under its term.
 */
export function fact(label, value, { absent = '—', ...extra } = {}) {
  return isMissing(value) ? { label, absent } : { label, value, ...extra }
}

/**
 * A row of Facts whose value is copied whole: kind 'url' (a URL or a path) or 'hex' (a digest, a serial)
 * in the shared chip, no kind for an identifier; its absence muted when there is none.
 */
export function copyRow(label, value, kind, extra = {}) {
  if (isMissing(value)) return { label, absent: '—', ...extra }
  const name = extra.copyLabel || label
  return kind ? { label, value: String(value), kind, long: kind === 'url', ...extra }
    : { label, value: <CodeValue value={value} label={name} />, ...extra }
}

/** A yes or no rule as the state of its row: a check and Oui, or a muted block sign and Non. */
export const yesNoState = (t, value) => (value ? ['', t('common.yes'), 'check'] : ['muted', t('common.no'), 'block'])
