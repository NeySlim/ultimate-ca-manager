/** runEach runs the unit calls in turn and keeps each outcome; BulkOutcome reads them line by line. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const i18n = vi.hoisted(() => ({ current: null }))
vi.mock('react-i18next', () => ({ useTranslation: () => i18n.current }))
import { frI18n } from './frI18n'
i18n.current = frI18n

import { runEach } from '../runEach'
import { BulkOutcome } from '../BulkOutcome'

describe('runEach', () => {
  it('calls one item after the other and keeps going past a failure', async () => {
    const order = []
    const out = await runEach([1, 2, 3], async (n) => {
      order.push(`start ${n}`)
      await Promise.resolve()
      order.push(`end ${n}`)
      if (n === 2) throw new Error('Request is already approved')
      return n * 10
    })
    expect(order).toEqual(['start 1', 'end 1', 'start 2', 'end 2', 'start 3', 'end 3'])
    expect(out).toEqual([
      { item: 1, ok: true, result: 10 },
      { item: 2, ok: false, reason: 'Request is already approved' },
      { item: 3, ok: true, result: 30 },
    ])
  })
})

describe('BulkOutcome', () => {
  it('says how many went through and why the others did not', () => {
    const onClose = vi.fn()
    render(<BulkOutcome onClose={onClose} nameOf={(n) => `#${n}`}
      outcome={[{ item: 1, ok: true }, { item: 2, ok: false, reason: 'Request has expired' }, { item: 3, ok: true }]} />)
    expect(screen.getByRole('status')).toHaveTextContent('2 réussies, 1 échouée')
    const failed = screen.getByText('#2').closest('li')
    expect(failed).toHaveClass('is-failed')
    expect(failed).toHaveTextContent('Request has expired')
    fireEvent.click(screen.getByRole('button', { name: 'Fermer' }))
    expect(onClose).toHaveBeenCalled()
  })
})
