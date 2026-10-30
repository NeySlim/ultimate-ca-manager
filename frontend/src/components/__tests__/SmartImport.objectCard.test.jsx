/**
 * Smart import object card: a key the parser read but cannot use shows why,
 * and a size in bits appears only for a key that has one.
 */
import { render, screen } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, opts) => (opts && opts.name ? `${opts.name} (level ${opts.level})` : key) }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))

import { ObjectCard } from '../SmartImport'

const key = (fields) => ({
  type: 'private_key', index: 0, matched_key_index: null, is_encrypted: false, ...fields,
})
const show = (obj) => render(
  <ObjectCard obj={obj} expanded onToggle={() => {}} selected={false} onSelect={() => {}} />,
)

describe('smart import object card', () => {
  it('says why a key that was read cannot be used', () => {
    const error = 'The seed and the public part of the expanded key of this ML-DSA-65 private key do not match'
    show(key({ key_algorithm: 'invalid', key_size: 0, error }))
    expect(screen.getByText(error)).toBeInTheDocument()
    expect(screen.queryByText(/bits/)).toBeNull()
  })

  it('gives no size to a post-quantum key', () => {
    show(key({ key_algorithm: 'ML-DSA-65', key_size: null, security_level: 3 }))
    expect(screen.getByText('ML-DSA-65 (level 3)')).toBeInTheDocument()
    expect(screen.queryByText(/bits/)).toBeNull()
  })

  it('keeps the size of an RSA key', () => {
    show(key({ key_algorithm: 'RSA', key_size: 2048 }))
    expect(screen.getByText('RSA (2048 bits)')).toBeInTheDocument()
  })
})
