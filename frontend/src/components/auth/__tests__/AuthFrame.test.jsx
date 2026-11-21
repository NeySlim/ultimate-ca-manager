/** Sign-in frame: one titled card, theme and language at the top right, version and project link below. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const i18n = vi.hoisted(() => ({ language: 'en', changeLanguage: vi.fn() }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key, i18n }) }))
vi.mock('../../../i18n', () => ({
  languages: [{ code: 'en', name: 'English', flag: 'EN' }, { code: 'fr', name: 'Français', flag: 'FR' }],
}))
vi.mock('../../../contexts/ThemeContext', () => ({
  useTheme: () => ({ themeFamily: 'atelier', setThemeFamily: vi.fn(), mode: 'dark', setMode: vi.fn(), resolvedMode: 'dark', themes: [] }),
}))

import { AuthFrame, AuthField, PROJECT_URL } from '../AuthFrame'

const renderFrame = (props = {}) => render(
  <MemoryRouter>
    <AuthFrame title="Title" lead="Lead" {...props}>
      <AuthField id="f" label="Field" error={props.error}><input id="f" /></AuthField>
    </AuthFrame>
  </MemoryRouter>
)

describe('AuthFrame', () => {
  beforeEach(() => { vi.clearAllMocks(); localStorage.clear() })

  it('names its card by the title, with the lead and the footer', () => {
    renderFrame()
    expect(screen.getByRole('region', { name: 'Title' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { level: 1, name: 'Title' })).toHaveAttribute('tabindex', '-1')
    expect(screen.getByText('Lead')).toBeInTheDocument()
    const link = screen.getByRole('link', { name: 'GitHub' })
    expect(link).toHaveAttribute('href', PROJECT_URL)
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
    expect(screen.getByLabelText('Field')).toBeInTheDocument()
  })

  it("is the mockup's authPage() tree, drawn under the .atl scope", () => {
    const { container } = renderFrame()
    const root = container.firstElementChild
    expect(root).toHaveClass('atl')
    expect(root.firstElementChild).toHaveClass('skip')
    const app = root.querySelector(':scope > #app.auth-mode')
    const main = app.querySelector(':scope > main.auth#main')
    expect([...main.children].map(el => el.className)).toEqual(['auth-tools', 'auth-card', 'auth-foot'])
    const card = main.querySelector('section.auth-card')
    expect(card).toHaveAttribute('aria-labelledby', 'main-title')
    expect([...card.children].slice(0, 3).map(el => el.className || el.id)).toEqual(['auth-brand', 'main-title', 'auth-lead'])
    expect(card.querySelector('.auth-brand > strong')).toHaveTextContent('UCM')
    expect(main.querySelector('.auth-foot > a')).toHaveClass('text-link')
  })

  it('moves the focus to the page from the skip link, the address untouched', () => {
    renderFrame()
    // The click is cancelled: the browser writes no #main in the address
    expect(fireEvent.click(screen.getByText('auth.page.skipToContent'))).toBe(false)
    expect(document.activeElement).toBe(document.getElementById('main'))
  })

  it('shows a field error as text beside its field', () => {
    renderFrame({ error: 'Required.' })
    expect(screen.getByText('Required.').closest('.field-error')).toHaveAttribute('id', 'err-f')
    expect(screen.getByText('Required.').closest('.field')).toContainElement(screen.getByLabelText('Field'))
  })

  it('changes the language from its menu, by keyboard, and gives the focus back', () => {
    renderFrame()
    const button = screen.getByRole('button', { name: 'settings.language' })
    expect(button).toHaveAttribute('aria-haspopup', 'menu')
    fireEvent.click(button)
    expect(button).toHaveAttribute('aria-expanded', 'true')
    const current = screen.getByRole('menuitemradio', { name: /English/ })
    expect(current).toHaveAttribute('aria-checked', 'true')
    expect(document.activeElement).toBe(current)
    fireEvent.keyDown(current, { key: 'ArrowDown' })
    expect(document.activeElement).toBe(screen.getByRole('menuitemradio', { name: /Français/ }))
    fireEvent.click(document.activeElement)
    expect(i18n.changeLanguage).toHaveBeenCalledWith('fr')
    expect(localStorage.getItem('i18nextLng')).toBe('fr')
    expect(document.activeElement).toBe(button)
    expect(button).toHaveAttribute('aria-expanded', 'false')
  })

  it("lays the language menu out as the mockup's theme menu: same panel, items and check", () => {
    renderFrame()
    fireEvent.click(screen.getByRole('button', { name: 'settings.language' }))
    const menu = screen.getByRole('menu', { name: 'settings.language' })
    expect(menu.tagName).toBe('UL')
    expect(menu).toHaveClass('pop-menu', 'theme-menu')
    expect(menu.parentElement).toHaveClass('pop-wrap')
    expect(screen.getByRole('button', { name: 'settings.language' })).toHaveClass('icon-btn', 'quiet')
    const items = screen.getAllByRole('menuitemradio')
    for (const item of items) {
      expect(item.parentElement).toHaveAttribute('role', 'none')
      expect(item.querySelector('.pop-label')).not.toBeNull()
      expect(item.querySelector('.pop-check svg.icon')).not.toBeNull()
    }
    expect(items.map(i => i.tabIndex)).toEqual([-1, -1])
  })

  it('opens the language menu from its button with the arrows: down on the current, up on the last', () => {
    renderFrame()
    const button = screen.getByRole('button', { name: 'settings.language' })
    fireEvent.keyDown(button, { key: 'ArrowDown' })
    expect(button).toHaveAttribute('aria-expanded', 'true')
    expect(document.activeElement).toBe(screen.getByRole('menuitemradio', { name: /English/ }))
    // The theme menu beside it stays closed
    expect(screen.getByRole('button', { name: 'shell.theme.label' })).toHaveAttribute('aria-expanded', 'false')
    fireEvent.keyDown(document.activeElement, { key: 'Escape' })
    fireEvent.keyDown(button, { key: 'ArrowUp' })
    expect(document.activeElement).toBe(screen.getByRole('menuitemradio', { name: /Français/ }))
  })

  it('closes the language menu on Escape, focus back on its button', () => {
    renderFrame()
    const button = screen.getByRole('button', { name: 'settings.language' })
    fireEvent.click(button)
    fireEvent.keyDown(document.activeElement, { key: 'Escape' })
    expect(button).toHaveAttribute('aria-expanded', 'false')
    expect(document.activeElement).toBe(button)
  })

  it('offers the theme menu too', () => {
    renderFrame()
    expect(screen.getByRole('button', { name: 'shell.theme.label' })).toBeInTheDocument()
  })

  it('gives the browser bar the background of the theme, one tag, following a change of theme', async () => {
    document.querySelectorAll('meta[name="theme-color"]').forEach(m => m.remove())
    const root = document.documentElement
    root.style.setProperty('--bg', '#141b24')
    renderFrame()
    const metas = () => document.querySelectorAll('meta[name="theme-color"]')
    expect(metas()).toHaveLength(1)
    expect(metas()[0].content).toBe('#141b24')
    root.style.setProperty('--bg', '#f4f5fb')
    root.setAttribute('data-theme', 'aurore')
    await waitFor(() => expect(metas()[0].content).toBe('#f4f5fb'))
    expect(metas()).toHaveLength(1)
    root.removeAttribute('data-theme')
    root.style.removeProperty('--bg')
  })

  it('leaves the tools and footer out of a window of its own', () => {
    renderFrame({ tools: false, footer: false })
    expect(screen.queryByRole('button', { name: 'settings.language' })).toBeNull()
    expect(screen.queryByRole('link', { name: 'GitHub' })).toBeNull()
  })
})
