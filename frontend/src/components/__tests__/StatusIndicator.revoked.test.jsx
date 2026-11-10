/**
 * StatusIndicator — a revoked certificate is not "merely switched off"
 * (DUP-FE-013c).
 *
 * `revoked` used the same grey as inactive / disabled / offline, so the dot of
 * a revoked certificate was indistinguishable from a disabled row, while every
 * badge map in the app (useCertificateColumns, UserCertificatesPage,
 * InspectorObject) paints revoked as danger.
 */
import { describe, it, expect } from 'vitest'
import { render, cleanup } from '@testing-library/react'
import { StatusIndicator } from '../StatusIndicator'

const dotClass = (status) => {
  cleanup()
  const { container } = render(<StatusIndicator status={status} />)
  return container.querySelector('.rounded-full').className
}

describe('DUP-FE-013c — StatusIndicator colours', () => {
  it('paints a revoked dot with the danger colour of its siblings', () => {
    expect(dotClass('revoked')).toContain('status-danger-bg-solid')
  })

  it('does not paint revoked like inactive, disabled or offline', () => {
    const revoked = dotClass('revoked')
    expect(revoked).not.toBe(dotClass('inactive'))
    expect(revoked).not.toBe(dotClass('disabled'))
    expect(revoked).not.toBe(dotClass('offline'))
    expect(revoked).not.toContain('bg-text-tertiary')
  })

  it('agrees with the expired and danger entries of the same map', () => {
    expect(dotClass('revoked')).toBe(dotClass('expired'))
    expect(dotClass('revoked')).toBe(dotClass('danger'))
  })

  it('leaves the other statuses alone', () => {
    expect(dotClass('valid')).toContain('status-success-bg-solid')
    expect(dotClass('expiring')).toContain('status-warning-bg-solid')
    expect(dotClass('offline')).toContain('bg-text-tertiary')
    expect(dotClass('nonsense')).toContain('bg-text-tertiary')
  })
})
