/** The « ⋯ » of the Certificates zone dock (certMenu()): open its actions dialog, pick an action. */
import { fireEvent, screen, waitFor, within } from '@testing-library/react'

export async function openMoreActions() {
  const trigger = await waitFor(() => {
    const el = document.querySelector('[data-cert-menu]')
    if (!el) throw new Error('no « ⋯ » in the dock yet')
    return el
  })
  fireEvent.click(trigger)
  return screen.findByTestId('inspector-actions-dialog')
}

export async function chooseMoreAction(name) {
  fireEvent.click(within(await openMoreActions()).getByRole('button', { name }))
}
