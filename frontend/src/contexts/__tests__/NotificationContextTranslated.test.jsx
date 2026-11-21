/**
 * The confirmation and prompt dialogs speak the interface language: their default
 * buttons and title come from the catalogue, never an English literal.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen, act } from '@testing-library/react'

beforeAll(() => {
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
})

const FR = { 'common.cancel': 'Annuler', 'common.confirm': 'Confirmer', 'common.ok': 'OK', 'common.inputRequired': 'Saisie requise', 'common.closeWindow': 'Fermer la fenêtre' }
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => FR[k] ?? k }) }))

import { NotificationProvider, useNotification } from '../NotificationContext'

let api
function Probe() { api = useNotification(); return null }

describe('confirmation and prompt in the interface language', () => {
  it('confirm: translated title and Cancel, in the Atelier dialog', async () => {
    render(<NotificationProvider><Probe /></NotificationProvider>)
    await act(async () => { api.showConfirm('Quitter ?', { confirmText: 'Quitter la page', variant: 'danger' }) })
    const dialog = screen.getByRole('dialog', { name: 'Confirmer' })
    expect(dialog.tagName).toBe('DIALOG')
    expect(dialog.className).toBe('narrow')
    expect(screen.getByRole('button', { name: 'Annuler' })).toBeInTheDocument()
    expect(screen.queryByText('Cancel')).toBeNull()
    expect(screen.getByRole('button', { name: 'Quitter la page' }).className).toBe('btn danger')
  })

  it('prompt: translated buttons, Enter submits the typed value', async () => {
    render(<NotificationProvider><Probe /></NotificationProvider>)
    let value
    await act(async () => { api.showPrompt('Nom ?').then((v) => { value = v }) })
    expect(screen.getByRole('dialog', { name: 'Saisie requise' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Annuler' })).toBeInTheDocument()
    const input = screen.getByRole('textbox')
    await act(async () => {
      input.focus()
      const { fireEvent } = await import('@testing-library/react')
      fireEvent.change(input, { target: { value: 'atelier' } })
      fireEvent.submit(input.closest('form'))
    })
    expect(value).toBe('atelier')
  })
})
