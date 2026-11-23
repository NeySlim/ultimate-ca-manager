/**
 * The template form's subject examples are the CA form's, read from the language files: no
 * Californian example left in a French form.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'fr' } }), Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn(), showPrompt: vi.fn() }),
  useMobile: () => ({ isMobile: false }),
  useInspector: () => ({ openEntity: vi.fn(), closeWindow: vi.fn(), windows: [] }),
}))
vi.mock('../../hooks', async () => {
  const persisted = await vi.importActual('../../hooks/usePersistedState')
  const crud = await vi.importActual('../../hooks/useCRUDPage')
  return {
    usePersistedState: persisted.usePersistedState,
    useCRUDPage: crud.useCRUDPage,
    usePermission: () => ({ canWrite: () => true, canDelete: () => true, canRead: () => true, hasPermission: () => true }),
  }
})
vi.mock('../../services', () => ({
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }), update: vi.fn(), duplicate: vi.fn(), delete: vi.fn(), export: vi.fn() },
}))
vi.mock('../../services/eku.service', () => ({ ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) } }))

import TemplatesPage from '../TemplatesPage'

describe('Template form, subject examples', () => {
  it('takes the CA form\'s examples for country, state, locality and unit, pinned fields included', async () => {
    render(<MemoryRouter><TemplatesPage /></MemoryRouter>)
    fireEvent.click((await screen.findAllByRole('button', { name: 'templates.createTemplate' }))[0])
    const holder = (id) => document.getElementById(id)?.placeholder
    const expected = ['common.countryPlaceholder', 'common.statePlaceholder', 'cas.localityPlaceholder', 'csrs.departmentPlaceholder']
    expect(['tpl-c', 'tpl-st', 'tpl-l', 'tpl-ou'].map(holder)).toEqual(expected)
    if (document.getElementById('tpl-pin-c')) expect(['tpl-pin-c', 'tpl-pin-st', 'tpl-pin-l', 'tpl-pin-ou'].map(holder)).toEqual(expected)
  })
})
