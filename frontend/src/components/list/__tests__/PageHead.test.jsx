/**
 * PageHead: title, total in words, intent, actions on the right; ListButton is
 * the template's button, the main action marked as such.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'
import { PageHead, ListButton } from '../PageHead'

describe('PageHead', () => {
  it('shows the title as the page heading, with the total and the intent', () => {
    render(<PageHead title="Certificates" total="1,234 certificates" intent="Inspect, issue and maintain." />)
    const head = screen.getByRole('banner')
    expect(within(head).getByRole('heading', { level: 1 })).toHaveTextContent(/^Certificates$/)
    expect(within(head).getByText('1,234 certificates')).toBeInTheDocument()
    expect(within(head).getByText('Inspect, issue and maintain.')).toBeInTheDocument()
  })

  it('leaves out what it is not given', () => {
    const { container } = render(<PageHead title="Certificates" />)
    expect(container.querySelector('.lv-total')).toBeNull()
    expect(container.querySelector('.lv-intent')).toBeNull()
    expect(container.querySelector('.lv-actions')).toBeNull()
  })

  it('keeps a total of zero', () => {
    const { container } = render(<PageHead title="Certificates" total={0} />)
    expect(container.querySelector('.lv-total')).toHaveTextContent(/^0$/)
  })

  it('puts the actions after the text, in the order given', () => {
    render(
      <PageHead
        title="Certificates"
        actions={<><ListButton quiet>Import</ListButton><ListButton primary>Issue</ListButton></>}
      />,
    )
    const buttons = screen.getAllByRole('button')
    expect(buttons.map((b) => b.textContent)).toEqual(['Import', 'Issue'])
    expect(buttons[0].compareDocumentPosition(screen.getByRole('heading')) & Node.DOCUMENT_POSITION_PRECEDING).toBeTruthy()
  })
})

describe('ListButton', () => {
  it('never submits a form by accident and forwards what it is given', () => {
    const onClick = vi.fn()
    render(<form onSubmit={() => { throw new Error('submitted') }}><ListButton onClick={onClick} title="hint">Go</ListButton></form>)
    const button = screen.getByRole('button', { name: 'Go' })
    expect(button).toHaveAttribute('type', 'button')
    expect(button).toHaveAttribute('title', 'hint')
    fireEvent.click(button)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('marks the main action and the quiet one', () => {
    render(<><ListButton primary>Issue</ListButton><ListButton quiet>Import</ListButton><ListButton>Plain</ListButton></>)
    expect(screen.getByText('Issue')).toHaveClass('is-primary')
    expect(screen.getByText('Import')).toHaveClass('is-quiet')
    expect(screen.getByText('Plain')).not.toHaveClass('is-primary', 'is-quiet')
  })

  it('hides its icon from assistive technology and does nothing when disabled', () => {
    const onClick = vi.fn()
    const Icon = (props) => <svg data-testid="icon" {...props} />
    render(<ListButton icon={Icon} disabled onClick={onClick}>Compare</ListButton>)
    expect(screen.getByTestId('icon')).toHaveAttribute('aria-hidden', 'true')
    fireEvent.click(screen.getByRole('button', { name: 'Compare' }))
    expect(onClick).not.toHaveBeenCalled()
  })
})
