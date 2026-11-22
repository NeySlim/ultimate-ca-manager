/** The dock's Detach tool: offered with a title where a window can open, never on a phone. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const size = vi.hoisted(() => ({ isMobile: false }))
vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k, i18n: { language: 'fr' } }) }))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => ({ isMobile: size.isMobile }) }))

import { Dock, DockBody } from '../Dock'

const dock = (onDetach) => render(
  <Dock label="Inspecteur" tabsLabel="Ouverts" tabs={[{ key: 1, title: 'vpn', icon: 'cert' }]} activeKey={1} onClose={() => {}} onDetach={onDetach}>
    <DockBody icon="cert" title="vpn" sections={[['overview', 'Aperçu']]} section="overview" onSection={() => {}} sectionsLabel="Sections" idPrefix="w1-">
      <p>panneau</p>
    </DockBody>
  </Dock>,
)

beforeEach(() => { size.isMobile = false })

describe('Detach in the dock', () => {
  it('is a titled tool of the bar that detaches the object', () => {
    const onDetach = vi.fn()
    dock(onDetach)
    const button = screen.getByRole('button', { name: 'inspector.detach' })
    expect(button).toHaveAttribute('title', 'inspector.detach')
    expect(button.closest('.dock-tools')).not.toBeNull()
    fireEvent.click(button)
    expect(onDetach).toHaveBeenCalledTimes(1)
  })

  it('is absent without a window to open, and on a phone', () => {
    const { unmount } = dock(undefined)
    expect(screen.queryByRole('button', { name: 'inspector.detach' })).toBeNull()
    unmount()
    size.isMobile = true
    dock(vi.fn())
    expect(screen.queryByRole('button', { name: 'inspector.detach' })).toBeNull()
  })

  it('gives the body ids of its own when asked, so a window beside the dock does not repeat them', () => {
    dock(vi.fn())
    expect(screen.getByRole('tab', { name: 'Aperçu' })).toHaveAttribute('id', 'w1-tab-overview')
    expect(screen.getByRole('tabpanel')).toHaveAttribute('id', 'w1-detail-panel')
  })
})
