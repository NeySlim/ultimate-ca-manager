/** State blocks of any page: skeleton rows and cards, read error with Retry, empty block (and EmptyState on it). */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { MemoryRouter } from 'react-router-dom'
import { Plus, ShieldCheck } from '@phosphor-icons/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k }) }))

import { SkeletonRows, SkeletonCards, LoadError, EmptyBlock, skWidth } from '../StateBlocks'
import { EmptyState } from '../../EmptyState'

describe('SkeletonRows', () => {
  it('draws one bar per column on every row, announces once and hides the other rows', () => {
    render(<table><tbody><SkeletonRows rows={4} check actions columns={[
      { key: 'name', grow: true }, { key: 'state', kind: 'pill', width: 74 }, { key: 'due', width: 92 },
    ]} /></tbody></table>)
    const rows = document.querySelectorAll('tr.lv-sk-row')
    expect(rows).toHaveLength(4)
    expect(rows[0].querySelectorAll('td')).toHaveLength(5)
    expect(rows[0]).not.toHaveAttribute('aria-hidden')
    expect(rows[1]).toHaveAttribute('aria-hidden', 'true')
    expect(screen.getAllByRole('status')).toHaveLength(1)
    expect(rows[0].querySelector('.lv-sk.is-box')).not.toBeNull()
    expect(rows[0].querySelector('.lv-sk.is-pill').style.width).toBe('74px')
    expect(rows[2].querySelector('.lv-grow .lv-sk').style.width).toBe(skWidth(2, 45, 40))
  })
})

describe('SkeletonCards', () => {
  it('draws cards of three bars, busy and announced', () => {
    const { container } = render(<SkeletonCards count={3} />)
    expect(container.querySelector('[aria-busy="true"]')).not.toBeNull()
    const cards = container.querySelectorAll('.lv-sk-record')
    expect(cards).toHaveLength(3)
    expect(cards[0].querySelectorAll('.lv-sk')).toHaveLength(3)
    expect(screen.getByRole('status')).toHaveTextContent('table.loadingRows')
  })
})

describe('LoadError', () => {
  it('says what failed and why, and reads again on Retry', async () => {
    const onRetry = vi.fn()
    render(<MemoryRouter><LoadError title="Could not load" cause="503 from the server" onRetry={onRetry} journal="/audit" /></MemoryRouter>)
    const alert = screen.getByRole('alert')
    expect(within(alert).getByRole('heading', { level: 2 })).toHaveTextContent('Could not load')
    expect(alert).toHaveTextContent('503 from the server')
    await userEvent.click(within(alert).getByRole('button', { name: 'table.retry' }))
    expect(onRetry).toHaveBeenCalledTimes(1)
    expect(within(alert).getByRole('link')).toHaveAttribute('href', '/audit')
  })

  it('keeps Retry out of the write guard: reading again is not a write', () => {
    render(<MemoryRouter><LoadError title="Could not load" onRetry={() => {}} /></MemoryRouter>)
    expect(screen.getByRole('button', { name: 'table.retry' })).toHaveAttribute('data-write', 'false')
  })

  it('has no journal link for who may not read it', () => {
    render(<MemoryRouter><LoadError title="Could not load" onRetry={() => {}} /></MemoryRouter>)
    expect(screen.queryByRole('link')).toBeNull()
  })
})

describe('EmptyBlock and EmptyState', () => {
  it('marks a writing next action for the write guard, and leaves a reading one alone', () => {
    const { rerender } = render(<EmptyBlock title="None" action={{ label: 'Add', onClick: () => {}, write: true }} />)
    expect(screen.getByRole('button', { name: 'Add' })).toHaveAttribute('data-write')
    rerender(<EmptyBlock title="None" action={{ label: 'Reload', onClick: () => {} }} />)
    expect(screen.getByRole('button', { name: 'Reload' })).not.toHaveAttribute('data-write')
  })

  it('shows icon, why and the next action as a button', async () => {
    const onClick = vi.fn()
    const { container } = render(<EmptyBlock icon={ShieldCheck} title="No CA" description="Create a root." action={{ label: 'Create', onClick, primary: true, icon: Plus }} />)
    expect(container.firstChild).toHaveClass('lv-empty')
    expect(screen.getByRole('heading', { level: 3 })).toHaveTextContent('No CA')
    const button = screen.getByRole('button', { name: 'Create' })
    expect(button).toHaveClass('lv-btn', 'is-primary')
    await userEvent.click(button)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('leads to a page when the action is a route', () => {
    render(<MemoryRouter><EmptyBlock title="None" action={{ label: 'Open', to: '/settings' }} /></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Open' })).toHaveAttribute('href', '/settings')
  })

  it('EmptyState keeps its props and draws the empty block, with a secondary action by default', async () => {
    const onClick = vi.fn()
    const { container } = render(<EmptyState title="Nothing" description="Why" action={{ label: 'Do', onClick }} />)
    expect(container.firstChild).toHaveClass('lv-empty')
    expect(container.querySelector('.rounded-2xl')).toBeNull()
    const button = screen.getByRole('button', { name: 'Do' })
    expect(button).not.toHaveClass('is-primary')
    await userEvent.click(button)
    expect(onClick).toHaveBeenCalled()
  })
})
