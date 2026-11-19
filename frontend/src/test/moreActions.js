/**
 * Opens the menu of the remaining actions of a certificate in the inspector, the way a
 * keyboard does, and returns one of its items by its label.
 */
import { fireEvent, screen } from '@testing-library/react'

export function openMoreActions() {
  fireEvent.keyDown(screen.getByTitle('inspector.moreActionsShort'), { key: 'Enter' })
  return screen.getByRole('menu')
}

export function moreAction(label) {
  const menu = screen.queryByRole('menu') || openMoreActions()
  return [...menu.querySelectorAll('[role="menuitem"]')].find((item) => item.textContent === label) || null
}
