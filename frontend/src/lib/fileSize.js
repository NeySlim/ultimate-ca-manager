// A byte count as the file picker shows it: KB, MB, then GB with one decimal.
export function formatSize(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(0)}KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(0)}MB`
  return `${(bytes / 1024 / 1024 / 1024).toFixed(1)}GB`
}

// A byte count in the reader's language and units (« 2,5 Mo », « 2.5 MB »), base 1024.
export function formatBytes(bytes, locale) {
  const steps = [['byte', 1], ['kilobyte', 1024], ['megabyte', 1024 ** 2], ['gigabyte', 1024 ** 3], ['terabyte', 1024 ** 4]]
  const n = Math.max(0, Number(bytes) || 0)
  const [unit, base] = steps.reduce((pick, step) => (n >= step[1] ? step : pick), steps[0])
  const digits = base >= 1024 ** 2 ? 1 : 0
  try {
    // The narrow no-break space of some locales has no glyph in the interface font
    return new Intl.NumberFormat(locale, { style: 'unit', unit, unitDisplay: 'short', maximumFractionDigits: digits }).format(n / base).replace(/\u202f/g, '\u00a0')
  } catch {
    return `${(n / base).toFixed(digits)} ${unit}`
  }
}

// A server time « YYYY-MM-DD HH:MM:SS UTC » as an ISO instant the date formatter reads everywhere.
export function serverUtcToIso(text) {
  const m = /^(\d{4}-\d{2}-\d{2})[ T](\d{2}:\d{2}(?::\d{2})?)\s*UTC$/.exec(String(text || '').trim())
  return m ? `${m[1]}T${m[2]}Z` : text
}

// A percentage given as 0..100 in the reader's notation (« 55,8 % », « 55.8% »).
export function formatPercent(value, locale) {
  try {
    return new Intl.NumberFormat(locale, { style: 'percent', maximumFractionDigits: 1 }).format(Number(value) / 100).replace(/\u202f/g, '\u00a0')
  } catch {
    return `${value}%`
  }
}
