import { beforeEach, describe, expect, it, vi } from 'vitest'
import { act, render, screen } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  getPreferences: vi.fn(),
  persistPreference: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, values) => values?.version ? `${key}:${values.version}` : key,
  }),
}))

vi.mock('../../services', () => ({
  apiClient: { get: mocks.get },
}))

vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, username: 'user' } }),
}))

vi.mock('../../stores/userPreferencesStore', () => ({
  getPreferences: mocks.getPreferences,
  persistPreference: mocks.persistPreference,
}))

vi.mock('../Button', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
}))

import { UpdatePopup } from '../UpdatePopup'

const whatsNew = (version, baselineVersion) => ({
  data: {
    enabled: true,
    version,
    baseline_version: baselineVersion,
    installed_at: null,
    release_notes: '',
  },
})

describe('UpdatePopup baseline', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mocks.getPreferences.mockReturnValue({})
  })

  it('does not show the version that was already running when enabled', async () => {
    let resolveRequest
    mocks.get.mockReturnValue(new Promise((resolve) => { resolveRequest = resolve }))
    render(<UpdatePopup />)
    await vi.waitFor(() => expect(mocks.get).toHaveBeenCalled())
    await act(async () => { resolveRequest(whatsNew('2.217', '2.217')) })
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument()
  })

  it('shows a later version to a user without an acknowledgement', async () => {
    mocks.get.mockResolvedValue(whatsNew('2.218', '2.217'))
    render(<UpdatePopup />)
    expect(await screen.findByRole('dialog')).toHaveTextContent('updatePopup.title:2.218')
  })
})
