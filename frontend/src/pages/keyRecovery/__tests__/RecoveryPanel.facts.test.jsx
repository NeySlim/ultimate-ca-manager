/**
 * A key recovery request in typed rows: its state a pill, its reason and the decision's note on long rows, a missing
 * requester an absence, the certificate a link to it as an approval's is.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k, i18n: { language: 'en' } }) }))
const openEntity = vi.fn()
vi.mock('../../../hooks/useOpenEntity', () => ({ useOpenEntity: () => openEntity }))
vi.mock('../../../hooks', () => ({ usePermission: () => ({ hasPermission: () => true, username: 'bob' }) }))

import { RecoveryPanel } from '../KeyRecoveryDetail'

const REQ = {
  id: 12, cert_id: 7, cert_cn: 'vault.example.com', requested_by: null, requested_at: '2026-11-20T10:00:00Z', status: 'approved',
  reason: 'The holder left the company and the mailbox must be read for the audit of the quarter',
  decided_by: 'carol', decided_at: '2026-11-21T09:00:00Z', decision_note: 'Approved after the call with the legal department',
}
const row = (term) => [...document.querySelectorAll('dl.kv > div.row')].find((r) => r.querySelector('dt')?.textContent === term)

describe('the key recovery panel', () => {
  it('types the facts of a request and of its decision', () => {
    render(<RecoveryPanel req={REQ} />)
    expect(document.querySelector('dl.props')).toBeNull()
    expect(document.querySelectorAll('dl.kv')).toHaveLength(2)
    expect(row('approvals.work.detail.state').querySelector('dd.v .badge')).not.toBeNull()
    expect(row('keyRecovery.reason')).toHaveClass('long')
    expect(row('keyRecovery.work.dialog.note')).toHaveClass('long')
    const requester = row('approvals.requester').querySelector('dd')
    expect(requester).toHaveClass('absent')
    expect(requester).toHaveTextContent('—')
    expect(row('approvals.work.detail.id').querySelector('dd.v .mono')).toHaveTextContent('#12')
    fireEvent.click(row('keyRecovery.work.certificate').querySelector('dd.v button.text-link'))
    expect(openEntity).toHaveBeenCalledWith('certificate', 7)
    expect(screen.queryByText('keyRecovery.work.recoveredBy')).toBeNull()
  })
})
