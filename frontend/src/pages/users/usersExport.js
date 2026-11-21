/**
 * The account list as a CSV file. A cell that a spreadsheet would read as a formula
 * (= + - @, tab, carriage return) is prefixed with a quote, so opening the file runs nothing.
 */
const cell = (value) => {
  let s = value === null || value === undefined ? '' : String(value)
  if (/^[=+\-@\t\r]/.test(s)) s = `'${s}`
  return /[",\n\r;]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

export function usersCsv(users, { head, row }) {
  const lines = [head, ...users.map(row)].map((cells) => cells.map(cell).join(','))
  return new Blob([`${lines.join('\r\n')}\r\n`], { type: 'text/csv;charset=utf-8' })
}
