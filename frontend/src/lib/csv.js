// A text cell starting with one of these runs as a formula in a spreadsheet (OWASP CSV Injection)
const FORMULA = /^[=+\-@\t\r]/

/**
 * One RFC 4180 cell: a text a spreadsheet would run as a formula gets a leading quote, a number
 * stays a number; a cell holding a quote, a comma, a semicolon or a line break is quoted.
 */
export function csvCell(value) {
  if (value === null || value === undefined) return ''
  let text = String(value)
  if (typeof value === 'string' && FORMULA.test(text)) text = `'${text}`
  return /[",;\r\n]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text
}
