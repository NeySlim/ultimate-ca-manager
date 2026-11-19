/**
 * `required` on a Select blocks the form until a value is chosen; the prop
 * used to be dropped, so forms counting on it submitted an empty choice.
 */
import { describe, it, expect, vi, beforeAll } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { Select } from '../Select'

beforeAll(() => {
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
})

const OPTIONS = [{ value: 'a', label: 'Alpha' }, { value: '', label: 'None' }]

const form = (props) => {
  const onSubmit = vi.fn((e) => e.preventDefault())
  render(
    <form onSubmit={onSubmit}>
      <Select label="Parent" options={OPTIONS} onChange={() => {}} required {...props} />
      <button type="submit">go</button>
    </form>
  )
  return onSubmit
}

describe('Select required', () => {
  it('blocks the submit while nothing is chosen', () => {
    const onSubmit = form({ value: null })
    fireEvent.click(screen.getByText('go'))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('submits once a value is chosen', () => {
    const onSubmit = form({ value: 'a' })
    fireEvent.click(screen.getByText('go'))
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('counts an explicit empty option as chosen', () => {
    const onSubmit = form({ value: '' })
    fireEvent.click(screen.getByText('go'))
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('marks the label', () => {
    form({ value: 'a' })
    expect(screen.getByText('Parent').parentElement.textContent).toContain('*')
  })
})
