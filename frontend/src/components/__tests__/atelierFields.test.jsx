/**
 * Fields of the Atelier mockup (`.field`): a label naming the control, a hint under it,
 * and an error at the field (marked invalid, message linked) that replaces the hint.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

import { Textarea } from '../Textarea'
import { SelectComponent } from '../Select'

describe('Atelier fields', () => {
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
