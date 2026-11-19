/**
 * StatusPill, SourceLabel, EntityName and RowMark: the word carries the state,
 * icons are decoration, and a mark without words has a readable label.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { StatusPill, SourceLabel, EntityName, RowMark } from '../StatusPill'

const Icon = (props) => <svg data-testid="icon" {...props} />

describe('StatusPill', () => {
  it.each(['good', 'warn', 'bad', 'muted'])('says the state in words for the %s tone, with a decorative icon', (tone) => {
    const { container } = render(<StatusPill tone={tone} label="Valid" />)
    const pill = screen.getByText('Valid')
    expect(pill).toHaveClass('lv-pill', `is-${tone}`)
    const icons = container.querySelectorAll('svg')
    expect(icons).toHaveLength(1)
    expect(icons[0]).toHaveAttribute('aria-hidden', 'true')
  })

  it('falls back to the quiet tone for one it does not know', () => {
    render(<StatusPill tone="rainbow" label="Unknown" />)
    expect(screen.getByText('Unknown')).toHaveClass('is-muted')
    expect(screen.getByText('Unknown')).not.toHaveClass('is-rainbow')
  })

  it('takes the icon of the caller', () => {
    render(<StatusPill tone="good" icon={Icon} label="Valid" />)
    expect(screen.getByTestId('icon')).toHaveAttribute('aria-hidden', 'true')
  })

  it('carries no fill and no animated dot', () => {
    const { container } = render(<StatusPill tone="warn" label="To renew" />)
    expect(container.querySelector('[class*="animate"], [class*="pulse"], [class*="bg-"]')).toBeNull()
    expect(container.firstChild.children).toHaveLength(1)
  })
})

describe('SourceLabel', () => {
  it('is a quiet label with its icon', () => {
    render(<SourceLabel icon={Icon} label="ACME" />)
    expect(screen.getByText('ACME')).toHaveClass('lv-source')
    expect(screen.getByTestId('icon')).toHaveAttribute('aria-hidden', 'true')
  })

  it('renders nothing without a label', () => {
    const { container } = render(<SourceLabel icon={Icon} label="" />)
    expect(container).toBeEmptyDOMElement()
  })
})

describe('EntityName', () => {
  it('is a button whose click reaches the row that opens the detail', () => {
    const open = vi.fn()
    render(<table><tbody><tr onClick={open}><td><EntityName icon={Icon}>web.example.com</EntityName></td></tr></tbody></table>)
    const name = screen.getByRole('button', { name: 'web.example.com' })
    expect(name).toHaveAttribute('type', 'button')
    fireEvent.click(name)
    expect(open).toHaveBeenCalledTimes(1)
  })
})

describe('RowMark', () => {
  it('reads its label when it is an icon alone', () => {
    render(<RowMark icon={Icon} label="Private key held" />)
    const mark = screen.getByRole('img', { name: 'Private key held' })
    expect(mark).toHaveAttribute('title', 'Private key held')
    expect(mark).toHaveTextContent('')
  })

  it('shows a word beside the icon and takes a tone', () => {
    render(<RowMark icon={Icon} tone="warn" label="Its issuer is gone">Orphan</RowMark>)
    const mark = screen.getByRole('img', { name: 'Its issuer is gone' })
    expect(mark).toHaveTextContent('Orphan')
    expect(mark).toHaveClass('is-warn')
  })
})
