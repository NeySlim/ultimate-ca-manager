/**
 * Taking a CA offline in file_exported mode hands its key over, so the server
 * asks for read:private_keys (backend/api/v2/cas/crud.py). The dialog offers
 * that mode only to a principal the server would serve.
 */
import { fireEvent, render, screen } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))

let mockPermissions = []
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: () => ({ permissions: mockPermissions }),
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}))
vi.mock('../../services', () => ({
  casService: { takeOffline: vi.fn() },
}))

import { TakeOfflineModal } from '../cas/TakeOfflineModal'

const CA = { id: 3, descr: 'Probe CA', common_name: 'Probe CA', has_private_key: true }

function openForm() {
  render(<TakeOfflineModal open onClose={() => {}} ca={CA} />)
  fireEvent.click(screen.getByText('common.continue'))
}

describe('TakeOfflineModal offers the key file only with read:private_keys', () => {
  beforeEach(() => { mockPermissions = [] })

  it('hides file export from an Operator (write:cas, no read:private_keys)', () => {
    mockPermissions = ['read:cas', 'write:cas']
    openForm()
    expect(screen.getByText('cas.offlinePasswordProtected')).toBeInTheDocument()
    expect(screen.queryByText('cas.offlineFileExported')).toBeNull()
  })

  it('offers it to an admin', () => {
    mockPermissions = ['*']
    openForm()
    expect(screen.getByText('cas.offlineFileExported')).toBeInTheDocument()
  })

  it('offers it to a principal holding write:cas and read:private_keys', () => {
    mockPermissions = ['read:cas', 'write:cas', 'read:private_keys']
    openForm()
    expect(screen.getByText('cas.offlineFileExported')).toBeInTheDocument()
  })
})
