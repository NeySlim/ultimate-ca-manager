/**
 * ChainRepairBar surfaces keys shared by CAs holding distinct certificates
 * (a cross-certificate next to its root): reported, never merged.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../../../lib/utils', () => ({
  cn: (...a) => a.filter(Boolean).join(' '),
}))

import { ChainRepairBar } from '../ChainRepairBar'

const t = (key) => key
const bar = (stats) => (
  <ChainRepairBar data={{ task: {}, stats }} running={false} onRun={() => {}} canRunRepair t={t} />
)

describe('ChainRepairBar same-key finding', () => {
  it('shows the count when CAs share a key with distinct certificates', () => {
    render(bar({ total_cas: 4, orphan_cas: 0, same_key_distinct_certs: 2 }))
    const finding = screen.getByText(/dashboard\.chainRepairSameKey/)
    expect(finding.textContent).toContain('2')
  })

  it('shows nothing when there is none', () => {
    render(bar({ total_cas: 4, orphan_cas: 0, same_key_distinct_certs: 0 }))
    expect(screen.queryByText(/dashboard\.chainRepairSameKey/)).toBeNull()
  })
})
