/** Opening Settings asks each route once: the sections that need the same data share the request. */
import { describe, it, expect, vi, beforeAll, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'

let SettingsPage
let apiClient
let dropSharedRequests

beforeAll(async () => {
  // The three services run for real here, over the mocked HTTP client
  for (const name of ['cas', 'settings', 'system']) vi.doUnmock(`../../services/${name}.service`)
  vi.resetModules()
  ;({ apiClient } = await import('../../services/apiClient'))
  ;({ dropSharedRequests } = await import('../../lib/sharedRequest'))
  ;({ default: SettingsPage } = await import('../SettingsPage'))
})

beforeEach(() => {
  // An answer takes time, as on the network: the sections ask while it is in flight
  dropSharedRequests()
  apiClient.get.mockReset()
  apiClient.get.mockImplementation(() => new Promise((resolve) => setTimeout(() => resolve({ data: [] }), 20)))
})

describe('Settings page requests', () => {
  it.each(['/cas', '/settings/general', '/system/service/status'])('asks %s once', async (route) => {
    render(<MemoryRouter initialEntries={['/settings']}><SettingsPage /></MemoryRouter>)
    await new Promise((r) => setTimeout(r, 300))
    const asked = apiClient.get.mock.calls.map(([url]) => url).filter((url) => url === route)
    expect(asked, `${route} asked ${asked.length} times`).toHaveLength(1)
  })
})
