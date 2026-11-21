/**
 * The page head's hidden buttons on a phone: a « ⋯ » that lists them in the mockup's menu dialog,
 * nothing on a wider screen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', async () => {
  const { enI18n } = await import('../../../test/enT')
  return { useTranslation: () => enI18n, Trans: ({ children }) => children }
})
const layout = vi.hoisted(() => ({ isMobile: true }))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: layout.isMobile }) }))

import { PhoneMoreActions } from '../PhoneMoreActions'

const onImport = vi.fn()
const items = [
  { id: 'import', icon: 'upload', label: 'Import', write: true, onClick: onImport },
  { id: 'sync', icon: 'refresh', label: 'Sync', disabled: true, onClick: vi.fn() },
  false,
]

beforeEach(() => { layout.isMobile = true; onImport.mockReset() })

describe('PhoneMoreActions', () => {
  it('opens the hidden actions of the page head on a phone, and runs the one chosen', () => {
    render(<PhoneMoreActions title="Templates" items={items} />)
    fireEvent.click(screen.getByRole('button', { name: 'Other actions of Templates' }))
    const menu = screen.getByTestId('inspector-actions-dialog')
    expect(screen.getByRole('heading', { name: 'Page actions' })).toBeTruthy()
    // A disabled action is left out; a write keeps the write guard's mark
    const buttons = [...menu.querySelectorAll('.columns-list button')]
    expect(buttons.map((b) => b.textContent)).toEqual(['Import'])
    expect(buttons[0]).toHaveAttribute('data-write', '')
    fireEvent.click(buttons[0])
    expect(onImport).toHaveBeenCalledTimes(1)
    expect(screen.queryByTestId('inspector-actions-dialog')).toBeNull()
  })

  it('draws nothing on a wider screen, where the buttons show', () => {
    layout.isMobile = false
    const { container } = render(<PhoneMoreActions title="Templates" items={items} />)
    expect(container.innerHTML).toBe('')
  })

  it('draws nothing when no action is left', () => {
    const { container } = render(<PhoneMoreActions title="Templates" items={[items[1]]} />)
    expect(container.innerHTML).toBe('')
  })
})
