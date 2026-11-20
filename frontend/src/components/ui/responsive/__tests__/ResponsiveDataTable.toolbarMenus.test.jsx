/**
 * The menus of the list toolbar (a filter, « Filtres prédéfinis », « Exporter les données »)
 * answer Escape themselves, as every layer of the mockup does: the first Escape closes
 * the menu and gives the focus back to its button, the inspector closes on the next one.
 * Presets and export are the mockup's pop menus: role menu, items, arrows, Home, End, Tab.
 */
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showConfirm: vi.fn(), showPrompt: vi.fn() }),
  useMobile: () => ({ isMobile: false, isDesktop: true, isTouch: false }),
}))
vi.mock('../../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))
vi.mock('../../../../contexts/AuthContext', () => ({
  useAuth: () => ({ isAuthenticated: true, permissions: ['read:certificates'] }),
}))
vi.mock('../../../../services', () => ({
  certificatesService: { getById: vi.fn((id) => Promise.resolve({ data: { id, common_name: `c${id}.example.com` } })) },
  casService: { getById: vi.fn() },
  userCertificatesService: { getById: vi.fn() },
  truststoreService: { getById: vi.fn() },
}))
vi.mock('../../../../services/account.service', () => ({ accountService: { updatePreferences: vi.fn().mockResolvedValue({}) } }))
vi.mock('../../../inspector/certificate/CertificateDetail', () => ({
  CertificateDetail: ({ cert, section }) => <div data-testid="panel">{`${cert.common_name}:${section}`}</div>,
}))

import { InspectorProvider, useInspector } from '../../../../contexts/InspectorContext'
import { setAuthenticated } from '../../../../stores/userPreferencesStore'
import { InspectorDock } from '../../../inspector/InspectorDock'
import { ResponsiveDataTable } from '../ResponsiveDataTable'

const ROWS = [{ id: 1, name: 'one' }, { id: 2, name: 'two' }]

function Page() {
  const { openEntity } = useInspector()
  return (
    <>
      <button type="button" onClick={() => openEntity('certificate', 1)}>open-1</button>
      <ResponsiveDataTable variant="list" data={ROWS} columns={[{ key: 'name', header: 'Name' }]}
        searchable filterPresetsKey="test-presets" exportEnabled
        toolbarFilters={[{ key: 'state', type: 'multiSelect', value: [], onChange: () => {}, placeholder: 'All states',
          options: [{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }] }]} />
      <InspectorDock />
    </>
  )
}

const renderPage = async () => {
  localStorage.setItem('test-presets', JSON.stringify([{ id: 7, name: 'Mine', filters: { state: ['a'] } }]))
  render(<InspectorProvider><Page /></InspectorProvider>)
  fireEvent.click(screen.getByText('open-1'))
  await screen.findByText('c1.example.com:overview')
  // The dock takes the focus on opening; the menus are opened after that
  await waitFor(() => expect(screen.getByRole('tab', { name: 'c1.example.com' })).toHaveFocus())
}
const escape = (target = document.activeElement || document.body) => fireEvent.keyDown(target, { key: 'Escape' })
const dockShown = () => screen.queryByTestId('inspector-dock') !== null

describe('Menus of the list toolbar and Escape', () => {
  beforeEach(() => {
    localStorage.clear()
    setAuthenticated(false)
    window.innerWidth = 1600
    window.innerHeight = 1000
  })

  it('a filter menu takes the first Escape, the inspector the second', async () => {
    await renderPage()
    const trigger = screen.getByRole('button', { name: /All states/ })
    trigger.focus()
    fireEvent.click(trigger)
    expect(screen.getByText('A')).toBeInTheDocument()
    escape()
    await waitFor(() => expect(screen.queryByText('A')).toBeNull())
    expect(dockShown()).toBe(true)
    expect(trigger).toHaveFocus()
    escape()
    await waitFor(() => expect(dockShown()).toBe(false))
  })

  it.each([
    ['table.filterPresets'],
    ['table.exportData'],
  ])('the %s menu is a menu that takes the first Escape and gives the focus back', async (name) => {
    await renderPage()
    const trigger = screen.getByRole('button', { name })
    trigger.focus()
    fireEvent.click(trigger)
    const menu = screen.getByRole('menu')
    expect(trigger).toHaveAttribute('aria-haspopup', 'menu')
    expect(trigger).toHaveAttribute('aria-expanded', 'true')
    // Opening puts the focus on the first item, as the mockup's pop menus do
    await waitFor(() => expect(within(menu).getAllByRole('menuitem')[0]).toHaveFocus())
    escape()
    await waitFor(() => expect(screen.queryByRole('menu')).toBeNull())
    expect(dockShown()).toBe(true)
    expect(trigger).toHaveFocus()
    escape()
    await waitFor(() => expect(dockShown()).toBe(false))
  })

  it('a menu opened with the mouse, focus left on its button, still takes Escape first', async () => {
    await renderPage()
    const trigger = screen.getByRole('button', { name: 'table.exportData' })
    fireEvent.click(trigger)
    expect(screen.getByRole('menu')).toBeInTheDocument()
    escape(document.body)
    await waitFor(() => expect(screen.queryByRole('menu')).toBeNull())
    expect(dockShown()).toBe(true)
  })

  it('moves between the export items with the arrows, Home and End, and closes on Tab', async () => {
    await renderPage()
    const trigger = screen.getByRole('button', { name: 'table.exportData' })
    fireEvent.click(trigger)
    const items = within(screen.getByRole('menu')).getAllByRole('menuitem')
    expect(items.map((i) => i.textContent)).toEqual(['table.exportCSV', 'table.exportJSON'])
    await waitFor(() => expect(items[0]).toHaveFocus())
    fireEvent.keyDown(items[0], { key: 'ArrowDown' })
    expect(items[1]).toHaveFocus()
    fireEvent.keyDown(items[1], { key: 'ArrowDown' })
    expect(items[0]).toHaveFocus()
    fireEvent.keyDown(items[0], { key: 'End' })
    expect(items[1]).toHaveFocus()
    fireEvent.keyDown(items[1], { key: 'Home' })
    expect(items[0]).toHaveFocus()
    fireEvent.keyDown(items[0], { key: 'Tab' })
    await waitFor(() => expect(screen.queryByRole('menu')).toBeNull())
    expect(trigger).toHaveFocus()
    expect(dockShown()).toBe(true)
  })

  it('opens a menu from its button with the down arrow', async () => {
    await renderPage()
    const trigger = screen.getByRole('button', { name: 'table.exportData' })
    trigger.focus()
    fireEvent.keyDown(trigger, { key: 'ArrowDown' })
    const menu = screen.getByRole('menu')
    await waitFor(() => expect(within(menu).getAllByRole('menuitem')[0]).toHaveFocus())
  })

  it('moves between a preset and its delete item with Left and Right', async () => {
    await renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'table.filterPresets' }))
    const [apply, remove] = within(screen.getByRole('menu')).getAllByRole('menuitem')
    expect(apply).toHaveTextContent('Mine')
    expect(remove).toHaveAccessibleName('table.deletePreset')
    await waitFor(() => expect(apply).toHaveFocus())
    fireEvent.keyDown(apply, { key: 'ArrowRight' })
    expect(remove).toHaveFocus()
    fireEvent.keyDown(remove, { key: 'ArrowLeft' })
    expect(apply).toHaveFocus()
  })

  it('names the presets menu in sentence case, with no capitals heading', async () => {
    await renderPage()
    fireEvent.click(screen.getByRole('button', { name: 'table.filterPresets' }))
    const menu = screen.getByRole('menu', { name: 'table.filterPresets' })
    expect(menu).toHaveClass('ui-pop')
    expect(menu.querySelector('.uppercase')).toBeNull()
  })
})
