/**
 * The EST label mapping refuses to save while two rows share a label: the repeated row says so,
 * and nothing reaches the server until it is resolved.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ getConfig: vi.fn(), getAll: vi.fn(), updateConfig: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts?.key !== undefined ? `${key}:${opts.key}` : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn() }),
}))
vi.mock('../../hooks', () => ({
  usePermission: () => ({ hasPermission: () => true, canWrite: () => true }),
  useClipboard: () => ({ copy: vi.fn() }),
}))
vi.mock('../../services', () => ({
  estService: { getConfig: mocks.getConfig, getStats: vi.fn().mockResolvedValue({ data: {} }),
    updateConfig: mocks.updateConfig },
  casService: { getAll: mocks.getAll },
}))
vi.mock('../../components', async (orig) => ({
  ...(await orig()),
  ResponsiveLayout: ({ children }) => <div>{children}</div>,
}))

import ESTPage from '../ESTPage'

describe('ESTPage label mapping', () => {
  it('refuses to save while two rows share a label, naming the second', async () => {
    mocks.getConfig.mockResolvedValue({ data: { enabled: true, ca_id: 1, labels: { web: 'ca-sign' } } })
    mocks.getAll.mockResolvedValue({ data: [{ id: 1, refid: 'ca-sign', name: 'Signing CA', has_private_key: true }] })
    mocks.updateConfig.mockResolvedValue({})
    render(<ESTPage />)
    await screen.findByDisplayValue('web')
    fireEvent.click(screen.getByText('common.add'))
    const keys = () => screen.getAllByPlaceholderText('est.labelPlaceholder')
    fireEvent.change(keys()[1], { target: { value: 'web' } })

    fireEvent.click(screen.getByText('common.saveConfiguration'))
    expect(screen.getByText('common.duplicateKey:web')).toBeInTheDocument()
    expect(mocks.updateConfig).not.toHaveBeenCalled()

    fireEvent.change(keys()[1], { target: { value: 'mail' } })
    fireEvent.click(screen.getByText('common.saveConfiguration'))
    expect(mocks.updateConfig).toHaveBeenCalledTimes(1)
    expect(mocks.updateConfig.mock.calls[0][0].labels).toEqual({ web: 'ca-sign', mail: '' })
  })
})
