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
  data: { issued: section(), via_cross: section({ cross_certificates: [] }), deployments: section(),
    subordinate_cas: section(), crl_deployments: section(), note: 'n', ...over },
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

  it('asks for the usage only when the section is opened, once', async () => {
    mocks.getChainUsage.mockResolvedValue(usage())
    renderIt()
    await screen.findByText('chainUsage.title')
    expect(mocks.getChainUsage).not.toHaveBeenCalled()
    fireEvent.click(screen.getByText('chainUsage.title'))
    await screen.findByTestId('chain-usage-empty')
    fireEvent.click(screen.getByText('chainUsage.title'))
    fireEvent.click(screen.getByText('chainUsage.title'))
    expect(mocks.getChainUsage).toHaveBeenCalledTimes(1)
  })

  it('does not say nothing depends on the CA while a servable cross-certificate it issued is on offer', async () => {
    mocks.getChainUsage.mockResolvedValue(usage({
      via_cross: section({ cross_certificates: [{ id: 3, ca_id: 2, ca_name: 'Root B', served: false, servable: true }] }),
    }))
    renderIt()
    await open()
    expect(await screen.findByTestId('chain-usage-offered')).toBeInTheDocument()
    expect(screen.queryByTestId('chain-usage-empty')).toBeNull()
  })

  it('still says nothing depends on the CA when the only cross-certificates cannot be served', async () => {
    mocks.getChainUsage.mockResolvedValue(usage({
      via_cross: section({ cross_certificates: [{ id: 3, ca_id: 2, ca_name: 'Root B', served: false, servable: false }] }),
    }))
    renderIt()
    await open()
    expect(await screen.findByTestId('chain-usage-empty')).toBeInTheDocument()
    expect(screen.getByText(/chainUsage.notServable/)).toBeInTheDocument()
  })

  it('shows an error when the usage cannot be read', async () => {
    mocks.getChainUsage.mockRejectedValue(new Error('forbidden'))
    renderIt()
    await open()
    expect(await screen.findByTestId('chain-usage-error')).toBeInTheDocument()
    expect(screen.queryByTestId('chain-usage-empty')).toBeNull()
  })

  it('renders nothing for a pending CA', () => {
    const { container } = renderIt({ id: 1, pending: true })
    expect(container).toBeEmptyDOMElement()
    expect(mocks.getChainUsage).not.toHaveBeenCalled()
  })

  it('does not say nothing depends on the CA while an active sub-CA is left', async () => {
    mocks.getChainUsage.mockResolvedValue(usage({
      subordinate_cas: section({ count: 1, items: [{ id: 4, name: 'Int B', valid_to: '2027-01-01T00:00:00Z' }] }),
    }))
    renderIt()
    await open()
    expect(await screen.findByText('Int B')).toBeInTheDocument()
    expect(screen.queryByTestId('chain-usage-empty')).toBeNull()
  })

  it('does not say nothing depends on the CA while a CRL deployment is left', async () => {
    mocks.getChainUsage.mockResolvedValue(usage({
      crl_deployments: section({ count: 1, items: [{ id: 2, target: 'crl-host', ca_name: 'Root A', crl_path: '/srv/a.crl' }] }),
    }))
    renderIt()
    await open()
    expect(await screen.findByText('crl-host')).toBeInTheDocument()
    expect(screen.queryByTestId('chain-usage-empty')).toBeNull()
  })

  it('ignores the answer of a CA that is no longer shown', async () => {
    let resolveOld
    mocks.getChainUsage
      .mockImplementationOnce(() => new Promise(r => { resolveOld = r }))
      .mockResolvedValueOnce(usage({ issued: section({ count: 1, items: [{ ...cert, name: 'new-ca-cert' }] }) }))
    const { rerender } = renderIt()
    await open()
    rerender(<MemoryRouter><ChainUsageSection ca={{ id: 10, name: 'Root C' }} /></MemoryRouter>)
    expect(await screen.findByText('new-ca-cert')).toBeInTheDocument()
    resolveOld(usage({ issued: section({ count: 1, items: [{ ...cert, name: 'old-ca-cert' }] }) }))
    await Promise.resolve()
    await waitFor(() => expect(screen.queryByText('old-ca-cert')).toBeNull())
    expect(screen.getByText('new-ca-cert')).toBeInTheDocument()
  })

  it('asks again after a failure when the section is reopened', async () => {
    mocks.getChainUsage.mockRejectedValueOnce(new Error('boom')).mockResolvedValueOnce(usage())
    renderIt()
    await open()
    expect(await screen.findByTestId('chain-usage-error')).toBeInTheDocument()
    fireEvent.click(screen.getByText('chainUsage.title'))
    fireEvent.click(screen.getByText('chainUsage.title'))
    expect(await screen.findByTestId('chain-usage-empty')).toBeInTheDocument()
    expect(mocks.getChainUsage).toHaveBeenCalledTimes(2)
  })

  it('loads the new CA when the id changes while the section is open', async () => {
    mocks.getChainUsage.mockResolvedValue(usage())
    const { rerender } = renderIt()
    await open()
    await screen.findByTestId('chain-usage-empty')
    rerender(<MemoryRouter><ChainUsageSection ca={{ id: 10, name: 'Root C' }} /></MemoryRouter>)
    await waitFor(() => expect(mocks.getChainUsage).toHaveBeenCalledWith(10))
    expect(mocks.getChainUsage).toHaveBeenCalledTimes(2)
  })

  it('asks again for a CA that went pending and came back', async () => {
    mocks.getChainUsage.mockResolvedValue(usage())
    const { rerender } = renderIt()
    await open()
    await screen.findByTestId('chain-usage-empty')
    rerender(<MemoryRouter><ChainUsageSection ca={{ id: 9, pending: true }} /></MemoryRouter>)
    rerender(<MemoryRouter><ChainUsageSection ca={ca} /></MemoryRouter>)
    await open()
    await waitFor(() => expect(mocks.getChainUsage).toHaveBeenCalledTimes(2))
  })
})
