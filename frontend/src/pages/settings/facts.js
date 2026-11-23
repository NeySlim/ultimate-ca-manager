/** A fact of the settings, or its absence (the dash, muted, beside its term) when the value is missing. */
export const fact = (label, value, extra = {}) => (value === null || value === undefined || value === ''
  ? { label, absent: '—' }
  : { label, value, ...extra })
