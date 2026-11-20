/**
 * A toast on screen is Radix's highest layer and takes Escape first: typed in an Atelier
 * dialog, Escape still closes the dialog (and leaves the toast).
 */
import { useState } from 'react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }), initReactI18next: { type: '3rdParty', init: () => {} } }))

import { NotificationProvider, useNotification } from '../../../contexts/NotificationContext'
import { AtelierDialog } from '../AtelierDialog'

afterEach(cleanup)

let api
function Page({ onClose }) {
  api = useNotification()
  const [open, setOpen] = useState(true)
  return open ? <AtelierDialog title="Certificate issued" onClose={() => { onClose(); setOpen(false) }}><button type="button">Inspect</button></AtelierDialog> : null
}

describe('AtelierDialog under a toast', () => {
  it('closes on Escape typed in it while a toast is on screen', async () => {
    const onClose = vi.fn()
    render(<NotificationProvider><Page onClose={onClose} /></NotificationProvider>)
    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
    await act(async () => { api.showSuccess('CA created: Lab root') })
    expect(screen.getByText('CA created: Lab root')).toBeInTheDocument()
    await act(async () => { fireEvent.keyDown(document.activeElement, { key: 'Escape' }) })
    expect(onClose).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByText('CA created: Lab root')).toBeInTheDocument()
  })

  it('closes on Escape with no toast', async () => {
    const onClose = vi.fn()
    render(<NotificationProvider><Page onClose={onClose} /></NotificationProvider>)
    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
    await act(async () => { fireEvent.keyDown(document.activeElement, { key: 'Escape' }) })
    expect(onClose).toHaveBeenCalledTimes(1)
  })
})
