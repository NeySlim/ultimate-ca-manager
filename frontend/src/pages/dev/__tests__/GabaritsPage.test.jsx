/**
 * The gabarits demo draws every screen with the mockup's records, without an error: the list in
 * its states, the module list and its detail, the work queue, the form, the card.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'fr' } }),
  Trans: ({ i18nKey }) => i18nKey,
}))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: false }) }))

import GabaritsPage from '../GabaritsPage'

const at = (q) => render(<MemoryRouter initialEntries={[`/dev/gabarits?${q}`]}><GabaritsPage /></MemoryRouter>)

describe('the gabarits demo', () => {
  it.each([
    ['screen=certificates', 'Certificats', '.cert-table tbody tr:not(.sk-row)'],
    ['screen=certificates&state=loading', 'Certificats', '.cert-table tbody tr.sk-row'],
    ['screen=certificates&state=error', 'Certificats', '#load-error-certificates'],
    ['screen=certificates&state=empty', 'Certificats', '#empty-certificates'],
    ['screen=templates&item=tls-server', 'Modèles', '#inspector .module-detail'],
    ['screen=approvals', 'Approbations', '.work-row'],
    ['screen=settings', 'Paramètres', '#settings-form'],
  ])('%s', (q, title, sel) => {
    const { container } = at(q)
    expect(screen.getByRole('heading', { level: 1, name: title })).toBeInTheDocument()
    expect(container.querySelector(`.atl ${sel}`)).not.toBeNull()
  })
  it('screen=dashboard', () => {
    const { container } = at('screen=dashboard')
    expect(container.querySelectorAll('#card-activity .activity-row')).toHaveLength(5)
  })
})
