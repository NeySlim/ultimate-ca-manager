import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))

import { CertificateOnlyBadge } from '../CAListUtils'

const t = (key) => key

describe('CertificateOnlyBadge (#426)', () => {
  it('marks a root imported without its key', () => {
    render(<CertificateOnlyBadge ca={{ is_root: true, type: 'root', certificate_only: true }} t={t} />)
    expect(screen.getByText('cas.noPrivateKey')).toHaveAttribute('title', 'cas.noPrivateKeyBanner')
  })

  it('keeps the warning for an intermediate whose key is missing', () => {
    render(<CertificateOnlyBadge ca={{ is_root: false, type: 'intermediate', certificate_only: true }} t={t} />)
    expect(screen.getByText('cas.certificateOnly')).toHaveAttribute('title', 'cas.certificateOnlyBanner')
  })

  it('shows nothing for a CA that holds its key', () => {
    const { container } = render(<CertificateOnlyBadge ca={{ is_root: true, has_private_key: true, certificate_only: false }} t={t} />)
    expect(container).toBeEmptyDOMElement()
  })
})
