/**
 * RoleMappingEditor: base role and/or custom role per external group.
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

import RoleMappingEditor, { normalizeRoleEntry, serializeRoleEntry } from '../settings/RoleMappingEditor'

const ROLES = [
  { value: 'admin', label: 'Admin' },
  { value: 'viewer', label: 'Viewer' },
]

function Harness({ initial, onEmit, customRoles = ['Cert Ops', 'Helpdesk'] }) {
  const [value, setValue] = useState(initial)
  return (
    <RoleMappingEditor
      value={value}
      onChange={(v) => { setValue(v); onEmit?.(v) }}
      roleOptions={ROLES}
      customRoles={customRoles}
      keyLabel="group"
      keyPlaceholder="ext-group"
    />
  )
}

const triggers = () => screen.getAllByRole('combobox').map(c => c.textContent)

describe('serialization', () => {
  it('writes a plain string when only the base role is set', () => {
    expect(serializeRoleEntry({ role: 'admin', custom: '' })).toBe('admin')
  })
  it('writes an object as soon as a custom role is set', () => {
    expect(serializeRoleEntry({ role: '', custom: 'Cert Ops' })).toEqual({ role: null, custom_role: 'Cert Ops' })
    expect(serializeRoleEntry({ role: 'viewer', custom: 'Cert Ops' })).toEqual({ role: 'viewer', custom_role: 'Cert Ops' })
  })
  it('writes an empty value when nothing is chosen', () => {
    expect(serializeRoleEntry({ role: '', custom: '' })).toBe('')
  })
  it('reads both stored forms', () => {
    expect(normalizeRoleEntry('admin')).toEqual({ role: 'admin', custom: '' })
    expect(normalizeRoleEntry({ role: null, custom_role: 'Helpdesk' })).toEqual({ role: '', custom: 'Helpdesk' })
    expect(normalizeRoleEntry(undefined)).toEqual({ role: '', custom: '' })
  })
})

describe('RoleMappingEditor', () => {
  it('shows string and object entries', () => {
    render(<Harness initial={{ a: 'admin', b: { role: 'viewer', custom_role: 'Cert Ops' } }} />)
    expect(screen.getAllByPlaceholderText('ext-group').map(i => i.value)).toEqual(['a', 'b'])
    expect(triggers()).toEqual(['Admin', 'common.none', 'Viewer', 'Cert Ops'])
  })

  it('keeps showing a custom role that is no longer in the list', () => {
    render(<Harness initial={{ a: { role: null, custom_role: 'Gone' } }} />)
    expect(triggers()).toEqual(['common.none', 'Gone'])
  })

  it('keeps the string form when only the base role changes', () => {
    const onEmit = vi.fn()
    render(<Harness initial={{ a: 'admin' }} onEmit={onEmit} />)
    fireEvent.change(screen.getByPlaceholderText('ext-group'), { target: { value: 'a2' } })
    expect(onEmit).toHaveBeenLastCalledWith({ a2: 'admin' })
  })

  it('emits an object once a custom role is present', () => {
    const onEmit = vi.fn()
    render(<Harness initial={{ a: { role: null, custom_role: 'Helpdesk' } }} onEmit={onEmit} />)
    fireEvent.change(screen.getByPlaceholderText('ext-group'), { target: { value: 'a2' } })
    expect(onEmit).toHaveBeenLastCalledWith({ a2: { role: null, custom_role: 'Helpdesk' } })
  })

  it('adds an empty row that serializes to an empty value', () => {
    const onEmit = vi.fn()
    render(<Harness initial={{}} onEmit={onEmit} />)
    fireEvent.click(screen.getByText('common.add'))
    expect(onEmit).toHaveBeenLastCalledWith({ '': '' })
  })
})
