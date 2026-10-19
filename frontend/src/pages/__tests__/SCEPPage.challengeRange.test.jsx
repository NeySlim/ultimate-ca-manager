/**
 * The challenge validity field takes its bounds from the API, so the form
 * and the server accept the same range.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'

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
})

describe('SCEP challenge validity range', () => {
  it('uses the bounds the API reports', async () => {
    render(<MemoryRouter initialEntries={['/scep']}><SCEPPage /></MemoryRouter>)
    fireEvent.click((await screen.findAllByText('common.config'))[0])
    const label = await screen.findByText('scep.challengeValidity')
    const input = label.closest('div').querySelector('input')
    expect(input.getAttribute('min')).toBe('1')
    expect(input.getAttribute('max')).toBe('720')
  })
})
