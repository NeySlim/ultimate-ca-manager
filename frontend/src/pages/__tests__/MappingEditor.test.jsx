/**
 * MappingEditor — stable row identity while editing keys (#222)
 */
import { describe, it, expect, vi } from 'vitest'
import { useState } from 'react'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key) => key,
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

import MappingEditor from '../settings/MappingEditor'

// Controlled harness — mirrors how SsoProviderForm feeds value back in.
function Harness({ initial, onEmit }) {
  const [value, setValue] = useState(initial)
  return (
    <MappingEditor
      value={value}
      onChange={(v) => { setValue(v); onEmit?.(v) }}
      keyLabel="key"
      valueLabel="value"
      keyPlaceholder="ext-group"
      valuePlaceholder="role"
    />
  )
}

const keyInputs = () => screen.getAllByPlaceholderText('ext-group')
const valInputs = () => screen.getAllByPlaceholderText('role')

describe('MappingEditor', () => {
  it('renders one row per entry, in insertion order', () => {
    render(<Harness initial={{ staff: 'viewer', 'pki-admins': 'admin' }} />)
    expect(keyInputs().map(i => i.value)).toEqual(['staff', 'pki-admins'])
    expect(valInputs().map(i => i.value)).toEqual(['viewer', 'admin'])
  })

  it('keeps row position when editing a non-last key (#222)', () => {
    const onEmit = vi.fn()
    render(<Harness initial={{ staff: 'viewer', 'pki-admins': 'admin' }} onEmit={onEmit} />)

    fireEvent.change(keyInputs()[0], { target: { value: 'staffers' } })

    // Row stays first — no shuffle to the bottom.
    expect(keyInputs().map(i => i.value)).toEqual(['staffers', 'pki-admins'])
    expect(onEmit).toHaveBeenLastCalledWith({ staffers: 'viewer', 'pki-admins': 'admin' })
  })

  it('survives a transient key collision without destroying the other row', () => {
    const onEmit = vi.fn()
    render(<Harness initial={{ admins: 'admin', ops: 'operator' }} onEmit={onEmit} />)

    // Typing 'admins2' letter-by-letter passes through 'admins' (collision).
    fireEvent.change(keyInputs()[1], { target: { value: 'admins' } })
    expect(keyInputs()).toHaveLength(2)
    fireEvent.change(keyInputs()[1], { target: { value: 'admins2' } })

    expect(keyInputs().map(i => i.value)).toEqual(['admins', 'admins2'])
    expect(onEmit).toHaveBeenLastCalledWith({ admins: 'admin', admins2: 'operator' })
  })

  it('adds and removes rows by identity', () => {
    const onEmit = vi.fn()
    render(<Harness initial={{ a: '1', b: '2' }} onEmit={onEmit} />)

    fireEvent.click(screen.getByText('common.add'))
    expect(keyInputs()).toHaveLength(3)

    // Remove the middle row ('b') — not the last one.
    fireEvent.click(screen.getAllByLabelText('common.remove')[1])
    expect(keyInputs().map(i => i.value)).toEqual(['a', ''])
    expect(onEmit).toHaveBeenLastCalledWith({ a: '1', '': '' })
  })

  it('rebuilds rows when the parent swaps the value externally', () => {
    const { rerender } = render(
      <MappingEditor value={{ a: '1' }} onChange={() => {}} keyPlaceholder="ext-group" valuePlaceholder="role" keyLabel="k" valueLabel="v" />
    )
    rerender(
      <MappingEditor value={{ x: '9', y: '8' }} onChange={() => {}} keyPlaceholder="ext-group" valuePlaceholder="role" keyLabel="k" valueLabel="v" />
    )
    expect(keyInputs().map(i => i.value)).toEqual(['x', 'y'])
  })
})
