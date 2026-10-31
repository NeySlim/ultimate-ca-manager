/**
 * The certificate list marks each member of a hybrid pair (RFC 9763) as linked,
 * with its role, in a column of its own.
 */
import { render, renderHook, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { useCertificateColumns } from '../useCertificateColumns'

const t = (key, opts) => (opts?.id ? `${key}:${opts.id}` : key)
const column = () => renderHook(() => useCertificateColumns(t)).result.current
  .find(c => c.key === 'related_certificate_id')

describe('useCertificateColumns linked column', () => {
  it('badges a pair member with its role', () => {
    const col = column()
    expect(col.header).toBe('certificates.hybrid.column')
    render(col.render(12, { id: 11, related_certificate_id: 12, hybrid_role: 'classical' }))
    const badge = screen.getByTestId('hybrid-linked-badge')
    expect(badge).toHaveTextContent('certificates.hybrid.linked')
    expect(badge).toHaveAttribute('title', 'certificates.hybrid.roleClassical')
  })

  it('names the PQ member as such', () => {
    render(column().render(11, { id: 12, related_certificate_id: 11, hybrid_role: 'pq' }))
    expect(screen.getByTestId('hybrid-linked-badge')).toHaveAttribute('title', 'certificates.hybrid.rolePq')
  })

  it('leaves a single certificate blank', () => {
    const { container } = render(<>{column().render(null, { id: 3, related_certificate_id: null })}</>)
    expect(screen.queryByTestId('hybrid-linked-badge')).toBeNull()
    expect(container).toHaveTextContent('—')
  })
})
