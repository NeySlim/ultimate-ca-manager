import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const mocks = vi.hoisted(() => ({ getChainUsage: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, vars) => (vars ? `${key}:${Object.values(vars).join('|')}` : key) }),
}))
vi.mock('../../../contexts', () => ({ useNotification: () => ({}) }))
vi.mock('../../../services', () => ({ casService: mocks }))

import { ChainUsageSection } from '../ChainUsageSection'

const ca = { id: 9, name: 'Root A' }
const section = (over = {}) => ({ count: 0, items: [], truncated: false, ...over })
const usage = (over = {}) => ({
  data: { issued: section(), via_cross: section({ cross_certificates: [] }), deployments: section(), note: 'n', ...over },
})
const cert = { id: 5, name: 'web.example', cn: 'web.example', ca: 'Int B', valid_to: '2027-01-01T00:00:00Z' }

const renderIt = (c = ca) => render(<MemoryRouter><ChainUsageSection ca={c} /></MemoryRouter>)
const open = async () => { fireEvent.click(await screen.findByText('chainUsage.title')) }

describe('ChainUsageSection', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('says nothing depends on the CA when every count is zero', async () => {
    mocks.getChainUsage.mockResolvedValue(usage())
    renderIt()
    await open()
    expect(await screen.findByTestId('chain-usage-empty')).toBeInTheDocument()
    expect(mocks.getChainUsage).toHaveBeenCalledWith(9)
  })

  it('lists the certificates with a link and the cross-certificates involved', async () => {
    mocks.getChainUsage.mockResolvedValue(usage({
      issued: section({ count: 1, items: [cert] }),
      via_cross: section({ count: 1, items: [cert], cross_certificates: [{ id: 3, ca_id: 2, ca_name: 'Root B', served: true }] }),
      deployments: section({ count: 1, items: [{ id: 7, target: 'nginx-1', certificate_id: 5, certificate: 'web.example', variant: 'auto' }] }),
    }))
    renderIt()
    await open()
    const links = await screen.findAllByRole('link', { name: 'web.example' })
    expect(links.length).toBe(3)
    expect(links[0]).toHaveAttribute('href', '/certificates/5')
    expect(screen.queryByTestId('chain-usage-empty')).toBeNull()
    expect(screen.getByText('nginx-1')).toBeInTheDocument()
    expect(screen.getByText(/chainUsage.crossRow:3\|Root B/)).toBeInTheDocument()
  })

  it('flags a truncated list', async () => {
    mocks.getChainUsage.mockResolvedValue(usage({ issued: section({ count: 150, items: [cert], truncated: true }) }))
    renderIt()
    await open()
    expect(await screen.findByText('chainUsage.truncated:1')).toBeInTheDocument()
  })

  it('renders nothing when the usage cannot be read', async () => {
    mocks.getChainUsage.mockRejectedValue(new Error('forbidden'))
    const { container } = renderIt()
    await waitFor(() => expect(mocks.getChainUsage).toHaveBeenCalled())
    expect(container).toBeEmptyDOMElement()
  })

  it('does not ask for a pending CA', () => {
    renderIt({ id: 1, pending: true })
    expect(mocks.getChainUsage).not.toHaveBeenCalled()
  })
})
