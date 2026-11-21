import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

import CTSection from '../CTSection'
import { blockedWhileSuspended } from '../../../components/shell/__tests__/writeGuardProbe'

const renderWith = (ctSettings) => render(
  <CTSection ctSettings={ctSettings} setCtSettings={vi.fn()} ctLoading={false} ctSaving={false}
    ctNewLogUrl="" setCtNewLogUrl={vi.fn()} handleCtSave={vi.fn()}
    handleCtAddLogUrl={vi.fn()} handleCtRemoveLogUrl={vi.fn()} />
)

describe('CTSection: embedding depends on CT being enabled', () => {
  it('hides Embed SCTs and Require SCTs while CT is disabled', () => {
    renderWith({ enabled: false, embed_sct: true, required: true, log_urls: [] })
    expect(screen.queryByText('settings.ctEmbedSct')).toBeNull()
    expect(screen.queryByText('settings.ctRequired')).toBeNull()
  })

  it('shows them once CT is enabled', () => {
    renderWith({ enabled: true, embed_sct: true, required: false, log_urls: [] })
    expect(screen.getByText('settings.ctEmbedSct')).toBeInTheDocument()
    expect(screen.getByText('settings.ctRequired')).toBeInTheDocument()
  })
})

describe('CTSection write guard', () => {
  it('suspends Add a CT log URL with the other writes', () => {
    renderWith({ enabled: true, embed_sct: false, required: false, log_urls: [] })
    expect(blockedWhileSuspended(screen.getByText('settings.ctAddLogUrl').closest('button'))).toBe(true)
  })

  it('names the list of logs and offers to remove each one', () => {
    renderWith({ enabled: false, log_urls: ['https://log.example/ct/'] })
    const list = screen.getByRole('list', { name: 'settings.ctLogUrls' })
    expect(list).toHaveTextContent('https://log.example/ct/')
    expect(screen.getByRole('button', { name: 'common.delete https://log.example/ct/' })).toBeInTheDocument()
  })
})
