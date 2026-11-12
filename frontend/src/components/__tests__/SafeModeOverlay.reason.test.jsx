/**
 * SafeModeOverlay: a wrong master key in place is not reported as a missing one.
 */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k }) }))

import { SafeModeOverlay } from '../SafeModeOverlay'

function health(body) {
  globalThis.fetch = vi.fn().mockResolvedValue({ ok: true, json: () => Promise.resolve(body) })
}

describe('SafeModeOverlay: safe mode reason', () => {
  afterEach(() => { vi.restoreAllMocks() })

  it('says the key is missing when none is loaded', async () => {
    health({ safe_mode: true, safe_mode_reason: 'encryption_key_missing' })
    render(<SafeModeOverlay />)
    expect(await screen.findByText('safeMode.description')).toBeInTheDocument()
    expect(screen.queryByText('safeMode.mismatchDescription')).toBeNull()
  })

  it('says the key does not match when a wrong one is in place', async () => {
    health({ safe_mode: true, safe_mode_reason: 'encryption_key_mismatch' })
    render(<SafeModeOverlay />)
    expect(await screen.findByText('safeMode.mismatchDescription')).toBeInTheDocument()
    expect(screen.getByText('safeMode.mismatchStep1Title')).toBeInTheDocument()
    expect(screen.queryByText('safeMode.description')).toBeNull()
  })

  it('says the key is not the cluster\'s when the cluster was disabled under another one', async () => {
    health({ safe_mode: true, safe_mode_reason: 'encryption_kek_not_the_clusters' })
    render(<SafeModeOverlay />)
    expect(await screen.findByText('safeMode.foreignKekDescription')).toBeInTheDocument()
    expect(screen.getByText('safeMode.foreignKekStep1Title')).toBeInTheDocument()
    expect(screen.queryByText('safeMode.mismatchDescription')).toBeNull()
    expect(screen.queryByText('safeMode.lostKeyHint')).toBeNull()
  })
})
