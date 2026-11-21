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
import { render, screen } from '@testing-library/react'

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
