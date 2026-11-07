/**
 * DashboardPage: a banner says so while no master key is loaded, since private
 * keys are then written to the database unencrypted.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'
import { dashboardService } from '../../services/dashboard.service'

import DashboardPage from '../DashboardPage'

function renderWithStatus(keyEncryption) {
  dashboardService.getSystemStatus = vi.fn().mockResolvedValue({
    data: { key_encryption: keyEncryption },
  })
  return render(<MemoryRouter><DashboardPage /></MemoryRouter>)
}

describe('DashboardPage: master key banner', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    dashboardService.getStats = vi.fn().mockResolvedValue({ data: {} })
    dashboardService.getRecentCAs = vi.fn().mockResolvedValue({ data: [] })
    dashboardService.getActivityLog = vi.fn().mockResolvedValue({ data: [] })
    dashboardService.getCertificateTrend = vi.fn().mockResolvedValue({ data: [] })
    dashboardService.getNextExpirations = vi.fn().mockResolvedValue({ data: [] })
  })

  it('warns while no master key is loaded', async () => {
    renderWithStatus({ status: 'warning', message: 'No master key loaded' })
    expect(await screen.findByText('dashboard.keyEncryptionOffTitle')).toBeInTheDocument()
    expect(screen.getByRole('alert')).toHaveTextContent('dashboard.keyEncryptionOffDesc')
  })

  it('stays silent once the key is loaded', async () => {
    renderWithStatus({ status: 'online', message: 'Private keys encrypted' })
    await screen.findAllByText('UCM')
    expect(screen.queryByText('dashboard.keyEncryptionOffTitle')).toBeNull()
  })
})
