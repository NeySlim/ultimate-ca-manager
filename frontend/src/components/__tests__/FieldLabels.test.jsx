import { describe, it, expect } from 'vitest'
import { render, screen } from '@testing-library/react'
import { Input } from '../Input'
import { Textarea } from '../Textarea'
import { SelectComponent } from '../Select'

// A visible label names its field: assistive technologies and getByLabelText find it
describe('form field labels', () => {
  const options = [{ value: 'a', label: 'Alpha' }]

  it('Input', () => {
    render(<Input label="Common Name" />)
    expect(screen.getByLabelText(/Common Name/).tagName).toBe('INPUT')
  })

  it('Input keeps an id given by the caller', () => {
    render(<Input label="Email" id="mail" />)
    expect(screen.getByLabelText('Email').id).toBe('mail')
  })

  it('Textarea', () => {
    render(<Textarea label="PEM" />)
    expect(screen.getByLabelText('PEM').tagName).toBe('TEXTAREA')
  })

  it('Select', () => {
    render(<SelectComponent label="Key type" options={options} />)
    expect(screen.getByLabelText('Key type')).toHaveAttribute('role', 'combobox')
  })

  it('searchable Select', () => {
    render(<SelectComponent label="Issuer" options={options} searchable />)
    expect(screen.getByLabelText('Issuer').tagName).toBe('BUTTON')
  })
})
