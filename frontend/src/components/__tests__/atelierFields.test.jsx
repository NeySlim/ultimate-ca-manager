/**
 * Fields of the Atelier mockup (`.field`): a label naming the control, a hint under it,
 * and an error at the field (marked invalid, message linked) that replaces the hint.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

import { Input } from '../Input'
import { Textarea } from '../Textarea'
import { SelectComponent } from '../Select'

describe('Atelier fields', () => {
  it('Input: the error is at the field, linked to it, and replaces the hint', () => {
    render(<Input label="Port" helperText="1 to 65535." error="Port out of range." />)
    const input = screen.getByLabelText('Port')
    expect(input).toHaveAttribute('aria-invalid', 'true')
    const message = screen.getByText('Port out of range.')
    expect(message.className).toContain('ui-error')
    expect(input.getAttribute('aria-describedby')).toContain(message.id)
    expect(screen.queryByText('1 to 65535.')).not.toBeInTheDocument()
  })

  it('Input: the hint is linked to the control when there is no error', () => {
    render(<Input label="Port" helperText="1 to 65535." />)
    const input = screen.getByLabelText('Port')
    expect(input).not.toHaveAttribute('aria-invalid')
    expect(input.className).toContain('ui-control')
    expect(input.getAttribute('aria-describedby')).toBe(screen.getByText('1 to 65535.').id)
  })

  it('Input: the reveal button of a typed password has an accessible name', () => {
    render(<Input label="Password" type="password" value="secret" onChange={() => {}} />)
    expect(screen.getByRole('button', { name: 'auth.page.showPassword' })).toBeInTheDocument()
  })

  it('Textarea: same field, error linked', () => {
    render(<Textarea label="Reason" error="Required for a refusal." />)
    const area = screen.getByLabelText('Reason')
    expect(area.className).toContain('ui-control')
    expect(area).toHaveAttribute('aria-invalid', 'true')
    expect(area.getAttribute('aria-describedby')).toBe(screen.getByText('Required for a refusal.').id)
  })

  it('Select: the trigger is the 36 px field, marked invalid on error', () => {
    render(<SelectComponent label="Format" options={[{ value: 'pem', label: 'PEM' }]} error="Choose one." />)
    const trigger = screen.getByRole('combobox')
    expect(trigger.className).toContain('ui-select-trigger')
    expect(trigger).toHaveAttribute('aria-invalid', 'true')
  })
})
