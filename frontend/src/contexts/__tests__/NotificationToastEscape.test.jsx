/**
 * A toast that arrives while a dialog is open sits above it in Radix's layer stack:
 * Escape typed in the dialog must still close the dialog, and leave the toast.
 */
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen } from '@testing-library/react'
import { useState } from 'react'

import { NotificationProvider, useNotification } from '../NotificationContext'
import { ListDialog } from '../../components/list/ListDialog'

beforeAll(() => {
  global.ResizeObserver = class ResizeObserver {
    observe() {}
    unobserve() {}
    disconnect() {}
  }
})
afterEach(cleanup)

let api
function Page({ onOpenChange }) {
  api = useNotification()
  const [open, setOpen] = useState(true)
  return (
    <ListDialog open={open} onOpenChange={(v) => { onOpenChange(v); setOpen(v) }} title="Schedule a report">
      <input aria-label="Sending time" />
    </ListDialog>
  )
}

describe('Escape in a dialog with a toast on screen', () => {
  it('closes the dialog and leaves the toast', async () => {
    const onOpenChange = vi.fn()
    render(<NotificationProvider><Page onOpenChange={onOpenChange} /></NotificationProvider>)
    const field = screen.getByLabelText('Sending time')
    field.focus()
    await act(async () => { api.showSuccess('Certificate issued: web01') })
    expect(screen.getByText('Certificate issued: web01')).toBeInTheDocument()
    await act(async () => { fireEvent.keyDown(field, { key: 'Escape' }) })
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(onOpenChange).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(screen.getByText('Certificate issued: web01')).toBeInTheDocument()
  })

  it('without a toast, closes the dialog once', async () => {
    const onOpenChange = vi.fn()
    render(<NotificationProvider><Page onOpenChange={onOpenChange} /></NotificationProvider>)
    const field = screen.getByLabelText('Sending time')
    field.focus()
    await act(async () => { fireEvent.keyDown(field, { key: 'Escape' }) })
    expect(onOpenChange).toHaveBeenCalledTimes(1)
    expect(screen.queryByRole('dialog')).toBeNull()
  })

  it('Escape outside any dialog still closes the toast', async () => {
    render(<NotificationProvider><Probe /></NotificationProvider>)
    await act(async () => { api.showSuccess('Saved.') })
    await act(async () => { fireEvent.keyDown(document.body, { key: 'Escape' }) })
    expect(screen.queryByText('Saved.')).toBeNull()
  })
})

function Probe() {
  api = useNotification()
  return null
}
