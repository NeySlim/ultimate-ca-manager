/**
 * Test helpers for the module lists drawn from the Atelier mockup: a row opens from its name button
 * (the first button of its table row or phone record), found by any text the row shows.
 */
import { screen, fireEvent, within } from '@testing-library/react'

export async function openRow(text) {
  const cells = await screen.findAllByText(text)
  const cell = cells.find((c) => c.closest('tr, article.mobile-record'))
  if (!cell) throw new Error(`no row shows ${text}`)
  const row = cell.closest('tr, article.mobile-record')
  fireEvent.click(within(row).getAllByRole('button')[0])
  return row
}
