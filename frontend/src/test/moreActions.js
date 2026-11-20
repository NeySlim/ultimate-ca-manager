/** The « ⋯ » menu of an inspector heading: open it with the keyboard, pick an action. */
import { fireEvent, screen, within } from '@testing-library/react'

export async function openMoreActions() {
  const trigger = await screen.findByTestId('inspector-more-actions')
  trigger.focus()
  fireEvent.keyDown(trigger, { key: 'Enter' })
  return screen.getByRole('menu')
}

export async function chooseMoreAction(name) {
  fireEvent.click(within(await openMoreActions()).getByRole('menuitem', { name }))
}
