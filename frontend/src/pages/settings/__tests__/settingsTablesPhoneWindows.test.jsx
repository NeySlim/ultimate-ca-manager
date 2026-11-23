/**
 * On a phone the Active Directory connectors and the Windows profiles become cards: a card keeps the
 * row actions (test, enable or disable, delete), which the form a record opens does not hold.
 */
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const mocks = vi.hoisted(() => ({
  t: (key) => key,
  notify: { showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn() },
  connectors: { list: vi.fn(), update: vi.fn(), create: vi.fn(), remove: vi.fn(), test: vi.fn() },
  profiles: { list: vi.fn(), update: vi.fn(), remove: vi.fn() },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: mocks.t, i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() } }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../contexts/MobileContext', () => ({
  useMobile: () => ({ isMobile: true, isTablet: false, isDesktop: false, isTouch: true, screenWidth: 390 }),
  MobileProvider: ({ children }) => children,
}))
vi.mock('../../../contexts', () => ({
  useNotification: () => mocks.notify,
  useMobile: () => ({ isMobile: true, isTablet: false, isDesktop: false, isTouch: true, screenWidth: 390 }),
}))
vi.mock('../../../services', () => ({ adConnectorsService: mocks.connectors, windowsProfilesService: mocks.profiles }))

import AdConnectorSection from '../AdConnectorSection'
import WindowsProfileList from '../WindowsProfileList'

const render2 = (ui) => render(ui, { wrapper: MemoryRouter })

describe('settings lists on a phone', () => {
  it('keeps an Active Directory connector\'s actions on its card', async () => {
    const connector = { id: 3, name: 'corp', realm: 'CORP.EXAMPLE', servers: ['dc1.corp.example'], enabled: true }
    mocks.connectors.list.mockResolvedValue({ data: [connector] })
    const { findByText } = render2(<AdConnectorSection hasPermission={() => true} />)
    const card = (await findByText('corp')).closest('.mobile-record')
    expect(card).not.toBeNull()
    for (const label of ['adConnector.testConnection', 'common.delete']) expect(within(card).getByTitle(label)).toBeInTheDocument()
    fireEvent.click(within(card).getByTitle('common.disable'))
    expect(mocks.connectors.update).toHaveBeenCalled()
  })

  it('keeps a Windows profile\'s actions on its card', async () => {
    const profile = { id: 9, name: 'branch', realm: 'BRANCH.EXAMPLE', is_default: false, enabled: true, state: 'complete', issuing_ca_name: 'CA' }
    mocks.profiles.list.mockResolvedValue({ data: [profile], meta: { total: 1, page: 1, per_page: 25 } })
    const { findByText } = render2(<WindowsProfileList cas={[]} canWrite onEdit={vi.fn()} onCreate={vi.fn()} reloadKey={0} />)
    const card = (await findByText('branch')).closest('.mobile-record')
    expect(card).not.toBeNull()
    expect(within(card).getByTitle('common.delete')).toBeInTheDocument()
    expect(within(card).getByTitle('common.disable')).toBeInTheDocument()
  })
})
