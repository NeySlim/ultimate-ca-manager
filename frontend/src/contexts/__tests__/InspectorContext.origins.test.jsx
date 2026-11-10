/**
 * Inspector focus origins: closing everything hands the focus back only when
 * nothing else took it, and an origin lives as long as its object.
 */
import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter, Link } from 'react-router-dom'
import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key, fallback) => fallback ?? key }) }))
vi.mock('../AuthContext', () => ({ useAuth: () => ({ isAuthenticated: true }) }))

import { InspectorProvider, MAX_OPEN, useInspector } from '../InspectorContext'
import { StatusFooter } from '../../components/ui/StatusFooter'

let api
function Probe() {
  api = useInspector()
  return null
}

const flush = () => act(async () => { await Promise.resolve() })

describe('inspector focus origins', () => {
  beforeEach(() => { localStorage.clear() })

  it('leaves the focus on the link that closed the inspector by navigation', async () => {
    render(
      <MemoryRouter initialEntries={['/certificates']}>
        <InspectorProvider>
          <Probe />
          <button>opener</button>
          <Link to="/cas">go-cas</Link>
          <StatusFooter />
        </InspectorProvider>
      </MemoryRouter>,
    )
    const opener = screen.getByText('opener')
    opener.focus()
    act(() => api.openEntity('certificate', 1))
    const link = screen.getByText('go-cas')
    link.focus()
    fireEvent.click(link)
    await flush()
    expect(api.openCount).toBe(0)
    expect(link).toHaveFocus()
    expect(opener).not.toHaveFocus()
  })

  it('gives the focus back to the opener when the focus is nowhere', async () => {
    render(<InspectorProvider><Probe /><button>opener</button></InspectorProvider>)
    const opener = screen.getByText('opener')
    opener.focus()
    act(() => api.openEntity('certificate', 1))
    opener.blur()
    act(() => api.closeAll())
    await flush()
    expect(opener).toHaveFocus()
  })

  it('uses the latest opening of an object as its origin', async () => {
    render(<InspectorProvider><Probe /><button>first</button><button>second</button></InspectorProvider>)
    screen.getByText('first').focus()
    act(() => api.openEntity('certificate', 1))
    screen.getByText('second').focus()
    act(() => api.openEntity('certificate', 1))
    screen.getByText('second').blur()
    act(() => api.closeEntity('certificate:1'))
    await flush()
    expect(screen.getByText('second')).toHaveFocus()
  })

  it('forgets the origin of an object pushed out by the limit', async () => {
    render(<InspectorProvider><Probe /><button>evicted</button></InspectorProvider>)
    const evicted = screen.getByText('evicted')
    evicted.focus()
    act(() => api.openEntity('certificate', 0))
    evicted.blur()
    // Later objects carry origins that are gone from the page
    for (let i = 1; i <= MAX_OPEN; i++) act(() => api.openEntity('certificate', i, { origin: document.createElement('button') }))
    expect(api.opened.some((o) => o.key === 'certificate:0')).toBe(false)
    act(() => api.closeAll())
    await flush()
    expect(evicted).not.toHaveFocus()
  })
})
