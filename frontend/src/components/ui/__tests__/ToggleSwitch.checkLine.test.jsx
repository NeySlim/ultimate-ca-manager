/**
 * A setting on or off is the Atelier check line: a native checkbox named by its label,
 * the description linked to it (not part of the name), the whole line clickable.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { ToggleSwitch } from '../ToggleSwitch'

describe('ToggleSwitch as a check line', () => {
  it('is a checkbox named by its label, the description linked', () => {
    render(<ToggleSwitch checked label="Require 2FA" description="Every account signs in with two factors." onChange={() => {}} />)
    const box = screen.getByRole('checkbox', { name: 'Require 2FA' })
    expect(box).toBeChecked()
    expect(box).toHaveAccessibleDescription('Every account signs in with two factors.')
    expect(screen.queryByRole('switch')).not.toBeInTheDocument()
    expect(box.closest('label').className).toContain('ui-check-line')
  })

  it('reports the new state, from the box or from its label', () => {
    const onChange = vi.fn()
    render(<ToggleSwitch checked={false} label="Syslog" onChange={onChange} />)
    fireEvent.click(screen.getByRole('checkbox', { name: 'Syslog' }))
    expect(onChange).toHaveBeenLastCalledWith(true)
    fireEvent.click(screen.getByText('Syslog'))
    expect(onChange).toHaveBeenCalledTimes(2)
  })

  it('does nothing when disabled', () => {
    const onChange = vi.fn()
    render(<ToggleSwitch checked label="Locked" disabled onChange={onChange} />)
    const box = screen.getByRole('checkbox', { name: 'Locked' })
    expect(box).toBeDisabled()
    fireEvent.click(box)
    expect(onChange).not.toHaveBeenCalled()
  })

  it('without a label is a bare box that takes the name it is given', () => {
    render(<ToggleSwitch checked={false} aria-label="Enable" onChange={() => {}} />)
    expect(screen.getByRole('checkbox', { name: 'Enable' })).not.toBeChecked()
  })
})
