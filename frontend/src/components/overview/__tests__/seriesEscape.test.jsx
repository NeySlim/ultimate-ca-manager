/**
 * Escape on a chart read from the keyboard clears its cursor, not only the tooltip: a later render of
 * the card (its figures refreshed by an event) never brings back a tooltip the user dismissed.
 */
import { describe, it, expect } from 'vitest'
import { render, fireEvent, act, screen } from '@testing-library/react'
import { MirrorBars } from '../viz'

const bars = (round) => (
  <MirrorBars ok={[1, 2, 3]} failed={[0, 1, 0]} color="var(--s1)" label="ACME"
    tipModel={(i) => ({ title: `day ${i} (${round})`, rows: [{ label: 'ok', value: String(i) }] })} />
)

describe('a series chart and Escape', () => {
  it('keeps its tooltip closed across a re-render once Escape dismissed it', () => {
    const { container, rerender } = render(bars(1))
    const frame = container.querySelector('.mirror')
    act(() => frame.focus())
    fireEvent.keyDown(frame, { key: 'ArrowLeft' })
    expect(screen.getByRole('tooltip')).toBeTruthy()
    fireEvent.keyDown(frame, { key: 'Escape' })
    expect(screen.queryByRole('tooltip')).toBeNull()
    rerender(bars(2))
    expect(screen.queryByRole('tooltip')).toBeNull()
    expect(frame.querySelector('.day.on')).toBeNull()
    // The arrows start over from the last day
    fireEvent.keyDown(frame, { key: 'ArrowLeft' })
    expect(frame.querySelector('.day.on').dataset.day).toBe('2')
  })
})
