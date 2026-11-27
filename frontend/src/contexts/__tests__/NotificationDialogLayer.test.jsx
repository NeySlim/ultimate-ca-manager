/**
 * A message raised while a modal dialog is open (#456): the error of a form dialog is shown in
 * the dialog, above its buttons; any other message is drawn in the dialog as a popover, the top
 * layer above it, so it is neither under the backdrop nor inert.
 */
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }), initReactI18next: { type: '3rdParty', init: () => {} } }))

import { NotificationProvider, SENDING_MS, useNotification } from '../NotificationContext'
import { AtelierDialog } from '../../components/atelier/AtelierDialog'

let api
function Probe() {
  api = useNotification()
  return null
}

function FormDialog() {
  const [open, setOpen] = useState(true)
  if (!open) return <button type="button">Reopen</button>
  return (
    <AtelierDialog title="Create Template" onClose={() => setOpen(false)}>
      <form onSubmit={(e) => { e.preventDefault(); onSend() }}>
        <input aria-label="Template Name" />
        <label htmlFor="tpl-notes">Notes</label>
        <textarea id="tpl-notes" />
        <label><input type="checkbox" /> Default template</label>
        <div className="modal-actions">
          <button type="button" onClick={() => setOpen(false)}>Cancel</button>
          <button type="submit" className="btn primary">Create</button>
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

// What the dialog's form does when sent: set by each test
let onSend = () => {}
beforeEach(() => { onSend = () => {} })
const send = (dialog, name = 'Create') => act(async () => { fireEvent.click(within(dialog).getByRole('button', { name })) })

describe('the error of a form dialog', () => {
  it('is shown in the dialog above its buttons, as an alert, and not as a toast', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    onSend = () => api.showError('A template with this name exists.')
    await send(dialog)
    const alert = within(dialog).getByRole('alert')
    expect(alert).toHaveTextContent('A template with this name exists.')
    expect(alert).toHaveClass('notice', 'bad')
    expect(alert.parentElement).toHaveClass('modal-actions')
    expect(line()).not.toHaveClass('visible')
  })

  it('takes the warning tone for a warning, and gives way to a newer one of the same sending', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    onSend = () => { api.showWarning('Name required.') }
    await send(dialog)
    expect(within(dialog).getByRole('alert')).toHaveClass('warn')
    onSend = () => { api.showWarning('Name required.'); api.showError('Saving failed.') }
    await send(dialog)
    expect(within(dialog).getAllByRole('alert')).toHaveLength(1)
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Saving failed.')
  })

  it('is the answer to a sending that waited for the server', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    onSend = async () => { await new Promise((done) => setTimeout(done, 300)); api.showError('Saving failed.') }
    await send(dialog)
    await wait(400)
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Saving failed.')
  })

  it('goes at the next submit, with its close button, and with the dialog', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    onSend = () => api.showError('Saving failed.')
    await send(dialog)
    onSend = () => {}
    await send(dialog)
    expect(within(dialog).queryByRole('alert')).toBeNull()
    onSend = () => api.showError('Saving failed again.')
    await send(dialog)
    await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'common.closeMessage' })) })
    expect(within(dialog).queryByRole('alert')).toBeNull()
    onSend = () => api.showError('Saving failed once more.')
    await send(dialog)
    await wait(50)
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
    const dialog = await screen.findByRole('dialog')
    const again = vi.fn()
    onSend = () => api.showError('Relaunch failed.', { action: { label: 'Again', onClick: again } })
    await send(dialog)
    expect(line()).toHaveTextContent('Relaunch failed.')
  })
})

describe('a message that is not the answer to the form', () => {
  it('raised while the form was never sent (polling, another page) is a toast above the dialog', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    await act(async () => { api.showError('Background job failed.') })
    expect(within(dialog).queryByRole('alert')).toBeNull()
    expect(line()).toHaveTextContent('Background job failed.')
    expect(dialog.contains(line())).toBe(true)
  })

  it('raised after the answer to the sending is a toast', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    onSend = () => api.showError('Saving failed.')
    await send(dialog)
    await wait(50)
    await act(async () => { api.showWarning('Connection lost.') })
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Saving failed.')
    expect(line()).toHaveTextContent('Connection lost.')
  })

  it('raised after a Cancel click is a toast', async () => {
    function Kept() {
      return (
        <AtelierDialog title="Keep" onClose={() => {}}>
          <div className="modal-actions">
            <button type="button" className="btn" onClick={() => api.showError('Nothing to cancel.')}>Cancel</button>
          </div>
        </AtelierDialog>
      )
    }
    mount(<Kept />)
    const dialog = await screen.findByRole('dialog')
    await send(dialog, 'Cancel')
    expect(within(dialog).queryByRole('alert')).toBeNull()
    expect(line()).toHaveTextContent('Nothing to cancel.')
  })
})

describe('a sending that raises nothing', () => {
  it('lets a later message be a toast once its delay has run out', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    await send(dialog)
    await wait(SENDING_MS + 100)
    await act(async () => { api.showError('Background job failed.') })
    expect(within(dialog).queryByRole('alert')).toBeNull()
    expect(line()).toHaveTextContent('Background job failed.')
  })

  it('lets a later message be a toast once the dialog is used again', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    await send(dialog)
    await act(async () => { fireEvent.input(within(dialog).getByLabelText('Template Name'), { target: { value: 'x' } }) })
    await act(async () => { api.showError('Background job failed.') })
    expect(within(dialog).queryByRole('alert')).toBeNull()
    expect(line()).toHaveTextContent('Background job failed.')
  })
})

describe('a passing message raised by the sending', () => {
  it('does not take the answer: the error that follows is still shown in the dialog', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    onSend = async () => {
      api.showInfo('Saving...')
      await new Promise((done) => setTimeout(done, 300))
      api.showError('Saving failed.')
    }
    await send(dialog)
    await wait(400)
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Saving failed.')
  })
})

describe('a success raised by the sending', () => {
  it('ends the sending: a later error of a dialog left open is a toast', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    onSend = () => api.showSuccess('Saved.')
    await send(dialog)
    await wait(300)
    await act(async () => { api.showError('Background job failed.') })
    expect(within(dialog).queryByRole('alert')).toBeNull()
    expect(line()).toHaveTextContent('Background job failed.')
  })

  it('leaves an error raised in the same task to the dialog', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    onSend = () => { api.showSuccess('Template created.'); api.showError('Its first version failed.') }
    await send(dialog)
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Its first version failed.')
  })
})

describe('pointing in the dialog while its sending waits', () => {
  const waitingSend = () => async () => {
    await new Promise((done) => setTimeout(done, 300))
    api.showError('Saving failed.')
  }

  it('outside a control (a scroll on a phone) keeps the answer for the dialog', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    onSend = waitingSend()
    await send(dialog)
    await act(async () => { fireEvent.pointerDown(dialog.querySelector('form')) })
    await wait(400)
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Saving failed.')
  })

  it('on a field or a label keeps the answer for the dialog: only typing in it is a use', async () => {
    mount(<FormDialog />)
    const dialog = await screen.findByRole('dialog')
    onSend = waitingSend()
    await send(dialog)
    await act(async () => {
      fireEvent.pointerDown(within(dialog).getByLabelText('Template Name'))
      fireEvent.pointerDown(within(dialog).getByLabelText('Notes'))
      fireEvent.pointerDown(within(dialog).getByText('Notes'))
      fireEvent.pointerDown(within(dialog).getByText('Default template'))
    })
    await wait(400)
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Saving failed.')
  })

  it('on a control that acts (a button, a checkbox) ends the sending', async () => {
    for (const target of [(d) => within(d).getByRole('button', { name: 'Cancel' }), (d) => within(d).getByRole('checkbox')]) {
      const view = mount(<FormDialog />)
      const dialog = await screen.findByRole('dialog')
      onSend = waitingSend()
      await send(dialog)
      await act(async () => { fireEvent.pointerDown(target(dialog)) })
      await wait(400)
      expect(within(dialog).queryByRole('alert')).toBeNull()
      expect(line()).toHaveTextContent('Saving failed.')
      view.unmount()
    }
  })
})

describe('a dialog whose primary button is a click, not a submit', () => {
  function ClickDialog() {
    return (
      <AtelierDialog title="Restore" onClose={() => {}}>
        <div className="modal-actions">
          <button type="button" className="btn primary" onClick={() => onSend()}>Restore</button>
        </div>
      </AtelierDialog>
    )
  }

  it('shows the answer to the click in the dialog, and clears it at the next click', async () => {
    mount(<ClickDialog />)
    const dialog = await screen.findByRole('dialog')
    onSend = () => api.showError('Restore refused.')
    await send(dialog, 'Restore')
    expect(within(dialog).getByRole('alert')).toHaveTextContent('Restore refused.')
    onSend = async () => { await new Promise((done) => setTimeout(done, 300)) }
    await send(dialog, 'Restore')
    expect(within(dialog).queryByRole('alert')).toBeNull()
  })
})

describe('a message raised by the handler that closes its dialog', () => {
  // The dialog is gone before the message could be painted in it: it is an ordinary toast
  function ClosingDialog({ order, type }) {
    const notify = useNotification()
    const [open, setOpen] = useState(true)
    if (!open) return null
    const raise = () => (type === 'error' ? notify.showError : notify.showWarning)('Export cut short.')
    return (
      <AtelierDialog title="Export" onClose={() => setOpen(false)}>
        <div className="modal-actions">
          <button type="button" className="btn primary" onClick={() => {
            if (order === 'close-first') { setOpen(false); raise() } else { raise(); setOpen(false) }
          }}>Export</button>
        </div>
      </AtelierDialog>
    )
  }

  for (const [order, type] of [['close-first', 'error'], ['close-first', 'warning'], ['message-first', 'warning']]) {
    it(`shows as a toast (${order}, ${type})`, async () => {
      mount(<ClosingDialog order={order} type={type} />)
      const dialog = await screen.findByRole('dialog')
      await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Export' })) })
      await wait(50)
      expect(screen.queryByRole('dialog')).toBeNull()
      expect(line()).toHaveTextContent('Export cut short.')
      expect(line()).toHaveClass('visible')
    })
  }

  it('shows as a toast when the dialog closes later, before the notice was painted', async () => {
    function LateClose() {
      const notify = useNotification()
      const [open, setOpen] = useState(true)
      if (!open) return null
      return (
        <AtelierDialog title="Backup" onClose={() => setOpen(false)}>
          <div className="modal-actions">
            <button type="button" className="btn primary" onClick={() => {
              notify.showWarning('Backup cancelled.')
              queueMicrotask(() => setOpen(false))
            }}>Create</button>
          </div>
        </AtelierDialog>
      )
    }
    mount(<LateClose />)
    const dialog = await screen.findByRole('dialog')
    await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'Create' })) })
    await wait(50)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(line()).toHaveTextContent('Backup cancelled.')
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
