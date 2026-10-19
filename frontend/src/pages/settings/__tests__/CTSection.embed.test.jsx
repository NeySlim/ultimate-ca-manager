import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: (props) => <input {...props} />,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ children }) => <section>{children}</section>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))

vi.mock('../../../components/ui/ToggleSwitch', () => ({
  ToggleSwitch: ({ label }) => <label>{label}</label>,
}))

import CTSection from '../CTSection'

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
