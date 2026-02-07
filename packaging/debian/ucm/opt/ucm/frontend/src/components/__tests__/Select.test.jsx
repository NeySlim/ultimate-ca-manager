import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { SelectComponent } from '../Select'

describe('Select Component', () => {
  const defaultOptions = [
    { value: 'opt1', label: 'Option 1' },
    { value: 'opt2', label: 'Option 2' },
    { value: 'opt3', label: 'Option 3' },
  ]

  it('renders with label', () => {
    render(<SelectComponent label="Test Select" options={defaultOptions} />)
    expect(screen.getByText('Test Select')).toBeInTheDocument()
  })

  it('renders trigger button', () => {
    render(<SelectComponent options={defaultOptions} />)
    const trigger = screen.getByRole('combobox')
    expect(trigger).toBeInTheDocument()
  })

  it('shows placeholder', () => {
    render(<SelectComponent options={defaultOptions} placeholder="Select an option" />)
    expect(screen.getByText('Select an option')).toBeInTheDocument()
  })

  it('shows selected value', () => {
    render(<SelectComponent options={defaultOptions} value="opt2" />)
    expect(screen.getByText('Option 2')).toBeInTheDocument()
  })

  it('renders disabled state', () => {
    render(<SelectComponent options={defaultOptions} disabled />)
    const trigger = screen.getByRole('combobox')
    expect(trigger).toHaveAttribute('data-disabled')
  })

  it('shows error message', () => {
    render(<SelectComponent options={defaultOptions} error="Required field" />)
    expect(screen.getByText('Required field')).toBeInTheDocument()
  })

  it('applies custom className', () => {
    render(<SelectComponent options={defaultOptions} className="custom-class" />)
    const wrapper = screen.getByRole('combobox').closest('[class*="space-y"]')
    expect(wrapper.className).toContain('custom-class')
  })
})
