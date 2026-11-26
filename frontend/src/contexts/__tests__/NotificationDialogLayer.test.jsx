/**
 * A message raised while a modal dialog is open (#456): the error of a form dialog is shown in
 * the dialog, above its buttons; any other message is drawn in the dialog as a popover, the top
 * layer above it, so it is neither under the backdrop nor inert.
 */
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }), initReactI18next: { type: '3rdParty', init: () => {} } }))

import { NotificationProvider, useNotification } from '../NotificationContext'
import { AtelierDialog } from '../../components/atelier/AtelierDialog'

let api
function Probe() {
  api = useNotification()
  return null
}

function FormDialog({ onSubmit = () => {} }) {
  const [open, setOpen] = useState(true)
  if (!open) return <button type="button">Reopen</button>
  return (
    <AtelierDialog title="Create Template" onClose={() => setOpen(false)}>
      <form onSubmit={(e) => { e.preventDefault(); onSubmit() }}>
        <input aria-label="Template Name" />
        <div className="modal-actions">
          <button type="button" onClick={() => setOpen(false)}>Cancel</button>
          <button type="submit">Create</button>
        </div>
      </form>
    </AtelierDialog>
  )
}

function InfoDialog() {
  return <AtelierDialog title="Certificate details"><p>Details</p></AtelierDialog>
}

beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }) })
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

const line = () => document.getElementById('toast')
const wait = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })
const mount = (children) => render(<NotificationProvider><Probe />{children}</NotificationProvider>)

describe('the error of a form dialog', () => {
  it('is shown in the dialog above its buttons, as an alert, and not as a toast', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    await act(async () => { api.showError('A template with this name exists.') })
    const alert = within(dialog).getByRole('alert')
    expect(alert).toHaveTextContent('A template with this name exists.')
    expect(alert).toHaveClass('notice', 'bad')
    expect(alert.parentElement).toHaveClass('modal-actions')
    expect(line()).not.toHaveClass('visible')
  })

  it('takes the warning tone for a warning, and gives way to a newer one', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    await act(async () => { api.showWarning('Name required.') })
    expect(within(dialog).getByRole('alert')).toHaveClass('warn')
    await act(async () => { api.showError('Saving failed.') })
    expect(within(dialog).getAllByRole('alert')).toHaveLength(1)
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Saving failed.')
  })

  it('goes at the next submit, with its close button, and with the dialog', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    await act(async () => { api.showError('Saving failed.') })
    await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Create' })) })
    expect(within(dialog).queryByRole('alert')).toBeNull()
    await act(async () => { api.showError('Saving failed again.') })
    await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'common.closeMessage' })) })
    expect(within(dialog).queryByRole('alert')).toBeNull()
    await act(async () => { api.showError('Saving failed once more.') })
    await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Cancel' })) })
    expect(screen.queryByRole('alert')).toBeNull()
    expect(screen.queryByText('Saving failed once more.')).toBeNull()
  })

  it('stays a toast when no dialog is open, or when it carries an action', async () => {
    mount()
    await act(async () => { api.showError('Load failed.') })
    expect(line()).toHaveTextContent('Load failed.')
    cleanup()
    mount(<FormDialog />)
    await screen.findByRole('dialog')
    const again = vi.fn()
    await act(async () => { api.showError('Relaunch failed.', { action: { label: 'Again', onClick: again } }) })
    expect(line()).toHaveTextContent('Relaunch failed.')
  })
})

describe('a toast while a modal dialog is open', () => {
  it('is drawn in the dialog as a manual popover, and its button works there', async () => {
    // jsdom has no popover: the browser's methods stand in, the element stays hidden to its queries
    const shown = vi.fn()
    HTMLElement.prototype.showPopover = shown
    try {
      mount(<InfoDialog />)
      const dialog = await screen.findByRole('dialog')
      const again = vi.fn()
      await act(async () => { api.showError('Relaunch failed.', { action: { label: 'Again', onClick: again } }) })
      expect(dialog.contains(line())).toBe(true)
      expect(line()).toHaveAttribute('popover', 'manual')
      expect(shown).toHaveBeenCalled()
      expect(shown.mock.contexts.at(-1)).toBe(line())
      await act(async () => { fireEvent.click(within(line()).getByRole('button', { name: /Again/, hidden: true })) })
      expect(again).toHaveBeenCalledTimes(1)
    } finally {
      delete HTMLElement.prototype.showPopover
    }
  })

  it('moves into a dialog opened after it, and back out when the dialog goes', async () => {
    function Later() {
      const [open, setOpen] = useState(false)
      return (
        <>
          <button type="button" onClick={() => setOpen(true)}>Open</button>
          {open && <AtelierDialog title="Details" onClose={() => setOpen(false)}><p>Body</p></AtelierDialog>}
        </>
      )
    }
    mount(<Later />)
    await act(async () => { api.showSuccess('Saved.') })
    expect(line().closest('dialog')).toBeNull()
    expect(line()).not.toHaveAttribute('popover')
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Open' })) })
    await wait(10)
    expect(screen.getByRole('dialog').contains(line())).toBe(true)
    expect(line()).toHaveTextContent('Saved.')
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'common.closeWindow' })) })
    await wait(10)
    expect(line().closest('dialog')).toBeNull()
    expect(line()).toHaveTextContent('Saved.')
  })

  it('is announced once, from the dialog', async () => {
    mount(<InfoDialog />)
    const dialog = await screen.findByRole('dialog')
    await act(async () => { api.showInfo('Exported.') })
    await wait(50)
    expect(within(dialog).getAllByRole('status')).toHaveLength(1)
    expect(line()).toHaveAttribute('aria-live', 'off')
  })
})
