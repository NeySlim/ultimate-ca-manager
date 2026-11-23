/**
 * The challenge validity field takes its bounds from the API, so the form
 * and the server accept the same range: outside it, the form says so and saves nothing.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'

vi.mock('../../hooks', async (orig) => ({
  ...(await orig()),
  usePermission: () => ({ hasPermission: () => true, canWrite: () => true, canDelete: () => true }),
}))

import SCEPPage from '../SCEPPage'
import { scepService } from '../../services/scep.service'

// The shared setup mocks this service with a partial object; complete it here.
Object.assign(scepService, {
  getConfig: vi.fn().mockResolvedValue({ data: {
    enabled: true, challenge_validity: 24, challenge_validity_range: [1, 720],
  } }),
  getRequests: vi.fn().mockResolvedValue({ data: [] }),
  getStats: vi.fn().mockResolvedValue({ data: {} }),
  getProfiles: vi.fn().mockResolvedValue({ data: [] }),
  getChallenge: vi.fn().mockResolvedValue({ data: {} }),
  getChallengeStates: vi.fn().mockResolvedValue({ data: [] }),
})

describe('SCEP challenge validity range', () => {
  it('uses the bounds the API reports', async () => {
    scepService.updateConfig = vi.fn().mockResolvedValue({ data: {} })
    render(<MemoryRouter initialEntries={['/scep-config?tab=config']}><SCEPPage /></MemoryRouter>)
    const input = await screen.findByRole('textbox', { name: /scep.challengeValidity/ })
    expect(input.closest('.field')).toHaveTextContent('scep.challengeValidityHelp')
    fireEvent.change(input, { target: { value: '721' } })
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    expect(input).toHaveAttribute('aria-invalid', 'true')
    expect(scepService.updateConfig).not.toHaveBeenCalled()
    fireEvent.change(input, { target: { value: '720' } })
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    await waitFor(() => expect(scepService.updateConfig).toHaveBeenCalledWith(expect.objectContaining({ challenge_validity: 720 })))
  })
})
