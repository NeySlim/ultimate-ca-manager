/**
 * An object opened from any page shows in the dock its zone draws, as the mockup's openCert()
 * and navigate('cas'): an authority goes to the Authorities page, a certificate to the
 * Certificates page (its deep link), a trusted certificate to the Trust Store. Only the
 * Certificates page docks a certificate in place; a type no zone draws opens nothing.
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
const mountAt = (path) => render(<MemoryRouter initialEntries={[path]}><InspectorProvider><Probe /></InspectorProvider></MemoryRouter>)
const where = () => screen.getByTestId('where').textContent

describe('an object opened from any page', () => {
  it('takes an authority to the Authorities page with it selected, and docks nothing', () => {
    mountAt('/certificates')
    act(() => api.openEntity('ca', 12))
    expect(where()).toBe('/cas?authority=12')
    expect(api.opened).toEqual([])
  })

  it.each(['/cas', '/', '/approvals', '/ssh/certificates'])('takes a certificate opened on %s to the Certificates page, which docks it', (from) => {
    mountAt(from)
    act(() => api.openEntity('certificate', 3))
    expect(where()).toBe('/certificates/3')
    expect(api.opened).toEqual([])
  })

  it.each(['/certificates', '/certificates/9'])('docks a certificate in place on %s', (from) => {
    mountAt(from)
    act(() => api.openEntity('certificate', 3))
    expect(api.opened.map((o) => o.key)).toEqual(['certificate:3'])
    expect(where()).toBe(from)
  })

  it('takes a trusted certificate to the Trust Store, which opens it in its dock', () => {
    mountAt('/certificates')
    act(() => api.openEntity('truststore', 5))
    expect(where()).toBe('/truststore/5')
    expect(api.opened).toEqual([])
  })

  it.each(['user_certificate', 'approval', 'report', 'csr'])('opens nothing for a %s, which no inspector draws', (type) => {
    mountAt('/certificates')
    act(() => api.openEntity(type, 4))
    expect(api.opened).toEqual([])
    expect(where()).toBe('/certificates')
  })
})
