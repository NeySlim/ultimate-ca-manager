/**
 * The mockup's numeric, secret, list and segmented fields: a number typed in numeric mode as a short
 * field, a secret masked and kept from autofill, a list of addresses typed with commas whose refused
 * entries are named once the field is left, and a segmented choice named by its label.
 */
import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { NumberInput, SecretInput, ListInput, SegmentedField } from '../Form'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k }) }))

const isEmail = (v) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v)

describe('numeric and secret fields', () => {
  it('types a number as the mockup: text in numeric mode, a short field', () => {
    render(<NumberInput label="Port" value="587" onChange={() => {}} />)
    const box = screen.getByRole('textbox', { name: 'Port' })
    expect(box).toHaveAttribute('inputmode', 'numeric')
    expect(box.closest('.field')).toHaveClass('short')
  })

  it('masks a secret and keeps it from the browser autofill', () => {
    render(<SecretInput label="Mot de passe" value="" hasExistingValue onChange={() => {}} />)
    const box = screen.getByLabelText('Mot de passe')
    expect(box).toHaveAttribute('type', 'password')
    expect(box).toHaveAttribute('autocomplete', 'new-password')
    expect(box).toHaveAttribute('placeholder', '••••••••••••')
  })
})

function Recipients({ initial = [], onList }) {
  const [list, setList] = useState(initial)
  return (
    <>
      <ListInput label="Destinataires" value={list} validate={isEmail} invalidMessage={(bad) => `Invalide : ${bad.join(', ')}`}
        onChange={(next) => { setList(next); onList?.(next) }} />
      <button type="button" onClick={() => setList(['reset@example.com'])}>reset</button>
    </>
  )
}

describe('list field', () => {
  it('keeps what is typed, hands back the valid entries and names a refused one once left', () => {
    const onList = vi.fn()
    render(<Recipients onList={onList} />)
    const box = screen.getByLabelText('Destinataires')
    fireEvent.change(box, { target: { value: 'pki@example.com, ' } })
    expect(box).toHaveValue('pki@example.com, ')
    expect(onList).toHaveBeenLastCalledWith(['pki@example.com'])
    fireEvent.change(box, { target: { value: 'pki@example.com, faux' } })
    expect(box).not.toHaveAttribute('aria-invalid')
    fireEvent.blur(box)
    expect(box).toHaveAttribute('aria-invalid', 'true')
    expect(screen.getByText('Invalide : faux')).toBeInTheDocument()
    expect(onList).toHaveBeenLastCalledWith(['pki@example.com'])
    fireEvent.change(box, { target: { value: 'pki@example.com, ops@example.com' } })
    expect(box).not.toHaveAttribute('aria-invalid')
    expect(onList).toHaveBeenLastCalledWith(['pki@example.com', 'ops@example.com'])
  })

  it('shows a list set from outside (a reset) in place of what was typed', () => {
    render(<Recipients initial={['a@example.com']} />)
    const box = screen.getByLabelText('Destinataires')
    expect(box).toHaveValue('a@example.com')
    fireEvent.change(box, { target: { value: 'a@example.com, b@example.com' } })
    fireEvent.click(screen.getByText('reset'))
    expect(box).toHaveValue('reset@example.com')
  })
})

describe('segmented field', () => {
  it('names its group by the label and presses the chosen values', () => {
    const onPick = vi.fn()
    render(<SegmentedField label="Jours" hint="Avant l’échéance." options={[{ value: 30, label: '30 j' }, { value: 7, label: '7 j' }]}
      pressed={(v) => v === 7} onPick={onPick} />)
    const group = screen.getByRole('group', { name: 'Jours' })
    expect(group).toHaveClass('segmented')
    expect(group).toHaveAccessibleDescription('Avant l’échéance.')
    expect(screen.getByRole('button', { name: '7 j' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByRole('button', { name: '30 j' })).toHaveAttribute('aria-pressed', 'false')
    fireEvent.click(screen.getByRole('button', { name: '30 j' }))
    expect(onPick).toHaveBeenCalledWith(30)
  })
})
