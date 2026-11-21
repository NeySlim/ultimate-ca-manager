/**
 * An authority opens in the Authorities page, beside its hierarchy, as the mockup does: the
 * inspector navigates there instead of docking a CA tab. Outside a router it docks it as before.
 */
import { act, render, screen } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'

vi.mock('../AuthContext', () => ({ useAuth: () => ({ isAuthenticated: true }) }))

import { InspectorProvider, useInspector } from '../InspectorContext'

let api
function Probe() {
  api = useInspector()
  return <output data-testid="where">{useLocation().pathname}{useLocation().search}</output>
}

describe('an authority opened from any page', () => {
  it('goes to the Authorities page with it selected, and docks nothing', () => {
    render(<MemoryRouter initialEntries={['/certificates']}><InspectorProvider><Probe /></InspectorProvider></MemoryRouter>)
    act(() => api.openEntity('ca', 12))
    expect(screen.getByTestId('where').textContent).toBe('/cas?authority=12')
    expect(api.opened).toEqual([])
  })

  it('still docks a certificate', () => {
    render(<MemoryRouter initialEntries={['/cas']}><InspectorProvider><Probe /></InspectorProvider></MemoryRouter>)
    act(() => api.openEntity('certificate', 3))
    expect(api.opened.map((o) => o.key)).toEqual(['certificate:3'])
    expect(screen.getByTestId('where').textContent).toBe('/cas')
  })
})
