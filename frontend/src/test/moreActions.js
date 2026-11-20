/** The « ⋯ » of an inspector heading: open its actions dialog, pick an action. */
import { fireEvent, screen, within } from '@testing-library/react'

export async function openMoreActions() {
  const trigger = await screen.findByTestId('inspector-more-actions')
  fireEvent.click(trigger)
  return screen.getByTestId('inspector-actions-dialog')
}

export async function chooseMoreAction(name) {
  fireEvent.click(within(await openMoreActions()).getByRole('button', { name }))
}
