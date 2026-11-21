/**
 * The row actions of the ACME domain tables.
 *
 * These two tabs declared their buttons as an ordinary "actions" column. On the
 * desktop table that column was sized from a guess made on the name of its key and
 * wrapped in the truncation meant for long text, so on a laptop-width window two of
 * the three buttons were clipped off the row. In the card view, below 900px, a plain
 * column is not rendered at all, so the buttons simply vanished (#355).
 *
 * ResponsiveDataTable has `rowActions` for exactly this: a column of its own on the
 * table, and rendered inside the card on a narrow screen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

// The shared page setup keeps i18n working while stubbing the services away.
import '../../__tests__/pageRenderingSetup.jsx'

import DomainsTab from '../DomainsTab'
import LocalDomainsTab from '../LocalDomainsTab'

const DOMAINS = [{
  id: 1, domain: 'example.test', dns_provider_name: 'cf', dns_provider_type: 'cloudflare',
  issuing_ca_name: null, is_wildcard_allowed: true, auto_approve: false,
}]

const LOCAL_DOMAINS = [{
  id: 1, domain: 'internal.test', issuing_ca_name: null, is_wildcard_allowed: true,
  auto_approve: false, enabled: true,
}]

describe.each([
  // LocalDomainsTab has no "test DNS access" action, hence one less.
  ['DomainsTab', DomainsTab, DOMAINS, ['common.edit', 'common.delete', 'acme.testDnsAccess']],
  ['LocalDomainsTab', LocalDomainsTab, LOCAL_DOMAINS, ['common.edit', 'common.delete']],
])('%s row actions', (_name, Tab, data, expected) => {
  const handlers = {}

  const renderTab = () => {
    handlers.onEdit = vi.fn()
    handlers.onDelete = vi.fn()
    handlers.onTest = vi.fn()
    return render(
      <Tab
        acmeDomains={data}
        localDomains={data}
        dnsProviders={[{ id: 1, name: 'cf', provider_type: 'cloudflare' }]}
        cas={[]}
        onAdd={vi.fn()}
        onEdit={handlers.onEdit}
        onDelete={handlers.onDelete}
        onTest={handlers.onTest}
        canWrite
        canDelete
      />
    )
  }

  beforeEach(() => vi.clearAllMocks())

  it.each(expected)('offers the %s action on the row', (label) => {
    renderTab()
    expect(screen.getByTitle(label)).toBeInTheDocument()
  })

  it('runs the action it was given rather than opening the row', () => {
    renderTab()
    screen.getByTitle('common.delete').click()
    expect(handlers.onDelete).toHaveBeenCalledWith(data[0])
    expect(handlers.onEdit).not.toHaveBeenCalled()
  })

  it('keeps the actions in the actions column, before the chevron', () => {
    renderTab()
    const actions = document.querySelector('tbody .table-actions')
    expect(actions).toBeTruthy()
    for (const label of expected) expect(actions.querySelector(`[title="${label}"]`)).toBeTruthy()
  })
})

describe.each([
  ['DomainsTab', DomainsTab, ['acme.provider', 'acme.issuingCA', 'acme.wildcard', 'atelier.state']],
  ['LocalDomainsTab', LocalDomainsTab, ['acme.issuingCA', 'atelier.state']],
])('%s list', (_name, Tab, sortable) => {
  const many = Array.from({ length: 30 }, (_, i) => ({
    id: i + 1, domain: `d${String(30 - i).padStart(2, '0')}.example.test`, dns_provider_name: 'cf', issuing_ca_name: null, is_wildcard_allowed: i % 2 === 0, auto_approve: i === 4,
  }))
  const renderTab = () => render(
    <Tab acmeDomains={many} localDomains={many} dnsProviders={[]} cas={[]} onAdd={vi.fn()} onEdit={vi.fn()} onDelete={vi.fn()} onTest={vi.fn()} canWrite canDelete />,
  )

  it('sorts by domain first, then from each header, and pages by 25', () => {
    const { container } = renderTab()
    const names = () => [...container.querySelectorAll('tbody .entity-name')].map((b) => b.textContent)
    const footer = container.querySelector('footer.table-footer')
    expect(names()).toHaveLength(25)
    expect(names()[0]).toBe('d01.example.test')
    expect(footer).toHaveTextContent('table.range')
    fireEvent.click(screen.getByRole('button', { name: 'table.nextPage' }))
    expect(names()).toEqual(['d26.example.test', 'd27.example.test', 'd28.example.test', 'd29.example.test', 'd30.example.test'])
    fireEvent.click(screen.getByRole('button', { name: 'atelier.state' }))
    expect(names()[0]).toBe('d26.example.test')
    for (const name of sortable) {
      fireEvent.click(screen.getByRole('button', { name }))
      expect(screen.getByRole('columnheader', { name })).toHaveAttribute('aria-sort', 'ascending')
    }
  })
})
