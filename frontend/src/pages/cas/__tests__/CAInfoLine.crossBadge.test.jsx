import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('../../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))
vi.mock('../../../lib/caSelection', () => ({ needsKeyImport: () => false }))

import { CAInfoLine } from '../CAListUtils'

const t = (key) => key

describe('CAInfoLine cross-signed badge', () => {
  it('shows the badge when the CA carries a cross-certificate', () => {
    render(<CAInfoLine ca={{ certs: 0, cross_certificate_count: 1 }} t={t} />)
    expect(screen.getByTestId('cross-badge')).toBeInTheDocument()
  })

  it('shows none otherwise', () => {
    render(<CAInfoLine ca={{ certs: 0, cross_certificate_count: 0 }} t={t} />)
    expect(screen.queryByTestId('cross-badge')).toBeNull()
  })
})
