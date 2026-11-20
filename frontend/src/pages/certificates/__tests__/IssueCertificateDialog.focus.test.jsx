/**
 * Focus of the issue dialog: the first field takes it at the opening, also for a renewal,
 * it goes back to the button that opened the dialog, and a click beside the dialog closes nothing.
 */
import { useState } from 'react'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { LABEL } from './issueFormTestUtils'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))
vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showWarning: vi.fn(), showError: vi.fn(), showConfirm: vi.fn() }),
}))
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

import { IssueCertificateDialog } from '../IssueCertificateDialog'

const CERT = {
  id: 12, cn: 'fw.lan', issuer_name: 'Services CA', key_algorithm: 'RSA', key_type: 'RSA 2048',
  valid_from: '2026-01-01T00:00:00Z', valid_to: '2026-04-01T00:00:00Z', san_dns: '["fw.lan"]',
}

function Opener({ mode = 'issue', onOpenChange }) {
  const [open, setOpen] = useState(false)
  return (
    <>
      <button type="button" onClick={() => setOpen(true)}>opener</button>
      <IssueCertificateDialog open={open} mode={mode} certificate={mode === 'renew' ? CERT : null}
        cas={[{ id: 3, descr: 'Services CA', has_private_key: true }]}
        onOpenChange={(next) => { onOpenChange?.(next); setOpen(next) }} />
    </>
  )
}

const openWithKeyboard = () => {
  const opener = screen.getByRole('button', { name: 'opener' })
  opener.focus()
  fireEvent.click(opener)
  return opener
}

describe('IssueCertificateDialog focus', () => {
  beforeEach(() => vi.clearAllMocks())

  it('gives the focus to the first field of a renewal, inside the dialog', async () => {
    render(<Opener mode="renew" />)
    openWithKeyboard()
    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
    expect(document.activeElement).toBe(screen.getByLabelText(LABEL.template))
  })

  it('gives the focus back to the button that opened it', async () => {
    render(<Opener />)
    const opener = openWithKeyboard()
    const dialog = await screen.findByRole('dialog')
    await waitFor(() => expect(dialog.contains(document.activeElement)).toBe(true))
    fireEvent.keyDown(document.activeElement, { key: 'Escape' })
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull())
    await waitFor(() => expect(document.activeElement).toBe(opener))
  })

  it('stays open after a click beside it', async () => {
    const onOpenChange = vi.fn()
    render(<Opener onOpenChange={onOpenChange} />)
    openWithKeyboard()
    await screen.findByRole('dialog')
    await new Promise((r) => setTimeout(r, 0))
    fireEvent.pointerDown(document.body)
    fireEvent.mouseDown(document.body)
    await new Promise((r) => setTimeout(r, 0))
    expect(onOpenChange).not.toHaveBeenCalledWith(false)
    expect(screen.getByRole('dialog')).toBeTruthy()
  })
})
