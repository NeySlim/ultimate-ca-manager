import { csvCell } from '../../lib/csv'

/**
 * The account list as a CSV file. A cell that a spreadsheet would read as a formula
 * (= + - @, tab, carriage return) is prefixed with a quote, so opening the file runs nothing.
 */

export function usersCsv(users, { head, row }) {
  const lines = [head, ...users.map(row)].map((cells) => cells.map(csvCell).join(','))
  return new Blob([`${lines.join('\r\n')}\r\n`], { type: 'text/csv;charset=utf-8' })
}
