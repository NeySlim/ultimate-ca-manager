/** The Expiry Report tile reflects the Expiring Certificates schedule. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => opts?.defaultValue || key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(), showError: vi.fn(), showInfo: vi.fn(), showWarning: vi.fn(),
    showConfirm: vi.fn(),
  }),
  useMobile: () => ({ isMobile: false, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
}))

vi.mock('../../hooks', () => ({
  usePermission: () => ({ canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true }),
}))

vi.mock('../../services', () => ({
  reportsService: {
    getTypes: () => Promise.resolve({ data: {} }),
    getSchedule: () => Promise.resolve({ data: {
      expiring_certificates: { enabled: true, frequency: 'weekly', time: '08:00', recipients: [] },
    } }),
    getPdfTemplates: () => Promise.resolve({ data: { templates: {}, sections: [] } }),
  },
}))

import ReportsPage from '../ReportsPage'

describe('ReportsPage expiry tile', () => {
  it('shows Enabled when the expiring certificates report is scheduled', async () => {
    render(<MemoryRouter><ReportsPage /></MemoryRouter>)
    const label = await screen.findByText('reports.expiryReport')
    const tile = label.closest('div').parentElement
    expect(tile.textContent).toContain('common.enabled')
    expect(tile.textContent).not.toContain('common.disabled')
  })
})
