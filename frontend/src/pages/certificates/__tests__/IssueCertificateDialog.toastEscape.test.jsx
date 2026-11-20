/**
 * A toast that arrives while the issue dialog is open sits above it in Radix's layer stack:
 * Escape typed in the dialog still closes the dialog.
 */
import { useState } from 'react'
import { afterEach, beforeAll, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }), initReactI18next: { type: '3rdParty', init: () => {} } }))
vi.mock('../../../hooks', () => ({ usePermission: () => ({ hasPermission: () => true }) }))
vi.mock('../../../services', () => ({
  certificatesService: { create: vi.fn(), renew: vi.fn() },
  csrsService: { upload: vi.fn(), sign: vi.fn() },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [] }) },
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }), getForCA: vi.fn().mockResolvedValue({ data: [] }) },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
  policiesService: { getEffective: vi.fn().mockResolvedValue({ data: { allowed_key_types: null } }) },
  toolsService: { decodeCsr: vi.fn() },
}))

import { NotificationProvider, useNotification } from '../../../contexts/NotificationContext'
import { IssueCertificateDialog } from '../IssueCertificateDialog'

beforeAll(() => {
  global.ResizeObserver = class ResizeObserver { observe() {} unobserve() {} disconnect() {} }
})
afterEach(cleanup)

let api
function Page({ onOpenChange }) {
  api = useNotification()
  const [open, setOpen] = useState(true)
  return (
    <IssueCertificateDialog open={open} cas={[{ id: 3, descr: 'Services CA', has_private_key: true }]}
      onOpenChange={(next) => { onOpenChange(next); setOpen(next) }} />
  )
}

describe('IssueCertificateDialog under a toast', () => {
  it('closes on Escape typed in it while a toast is on screen', async () => {
    const onOpenChange = vi.fn()
    render(<NotificationProvider><Page onOpenChange={onOpenChange} /></NotificationProvider>)
    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
    await act(async () => { api.showSuccess('CA created: Lab root') })
    expect(screen.getByText('CA created: Lab root')).toBeInTheDocument()
    await act(async () => { fireEvent.keyDown(document.activeElement, { key: 'Escape' }) })
    expect(onOpenChange).toHaveBeenCalledWith(false)
    expect(screen.queryByRole('dialog')).toBeNull()
  })
})
