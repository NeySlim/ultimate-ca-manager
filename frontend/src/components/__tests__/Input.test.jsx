import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Input } from '../Input'

describe('Input Component', () => {
  it('renders with label', () => {
    render(<Input label="Email" />)
    expect(screen.getByText('Email')).toBeInTheDocument()
  })

  it('renders without label', () => {
    render(<Input placeholder="Enter text" />)
    expect(screen.getByPlaceholderText('Enter text')).toBeInTheDocument()
  })

  it('calls onChange when typing', () => {
    const handleChange = vi.fn()
    render(<Input onChange={handleChange} data-testid="input" />)
    
    const input = screen.getByTestId('input')
    fireEvent.change(input, { target: { value: 'test' } })
    
    expect(handleChange).toHaveBeenCalled()
  })

  it('shows required indicator when required', () => {
    render(<Input label="Email" required />)
    expect(screen.getByText('*')).toBeInTheDocument()
  })

  it('displays helper text', () => {
    render(<Input label="Password" helperText="Min 8 characters" />)
    expect(screen.getByText('Min 8 characters')).toBeInTheDocument()
  })

  it('displays error state', () => {
    render(<Input label="Email" error="Invalid email format" />)
    expect(screen.getByText('Invalid email format')).toBeInTheDocument()
  })

  it('is disabled when disabled prop is true', () => {
    render(<Input label="Email" disabled data-testid="input" />)
    expect(screen.getByTestId('input')).toBeDisabled()
  })

  it('accepts different types', () => {
    render(<Input type="password" label="Password" data-testid="input" />)
    const input = screen.getByTestId('input')
    expect(input).toHaveAttribute('type', 'password')
  })

  it('forwards value prop correctly', () => {
    render(<Input label="Name" value="John" onChange={() => {}} data-testid="input" />)
    expect(screen.getByTestId('input')).toHaveValue('John')
  })

  it('forwards ref correctly', () => {
    const ref = { current: null }
    render(<Input ref={ref} />)
    expect(ref.current).toBeInstanceOf(HTMLInputElement)
  })

  it('renders icon when provided', () => {
    render(<Input icon={<span data-testid="icon">🔍</span>} data-testid="input" />)
    expect(screen.getByTestId('icon')).toBeInTheDocument()
  })
})
