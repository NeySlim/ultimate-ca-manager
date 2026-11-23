/**
 * About names the version; the live state of the service (start, memory, Python, environment) is
 * told once, by the service status of General, not again 4 000 px further down.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }) }))
vi.mock('../../../services', () => ({
  systemService: {
    getServiceStatus: () => Promise.resolve({ data: { version: '3.0', python_version: '3.13.5', uptime_seconds: 60, memory_mb: 200, is_docker: false } }),
  },
}))
vi.mock('../../../contexts', () => ({ useNotification: () => ({ showError: vi.fn(), showSuccess: vi.fn() }) }))
vi.mock('../../../hooks', () => ({ usePermission: () => ({ isAdmin: () => false, hasPermission: () => false }) }))
vi.mock('../FipsPreflightPanel', () => ({ default: () => null }))
vi.mock('../CompliancePreflightPanel', () => ({ default: () => null }))

import AboutSection from '../AboutSection'

describe('About', () => {
  it('names the version and leaves the service state to General', async () => {
    render(<AboutSection />)
    expect(await screen.findByText('3.0')).toBeInTheDocument()
    expect(screen.getByText('settings.about.version')).toBeInTheDocument()
    for (const term of ['settings.about.pythonVersion', 'settings.about.started', 'settings.about.memory', 'settings.about.environment']) {
      expect(screen.queryByText(term)).toBeNull()
    }
  })
})
