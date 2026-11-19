/** Toasts sit at the bottom of the window: the top right corner holds the commands of the bar and of a page header. */
import { describe, it, expect } from 'vitest'
import { render, screen, act } from '@testing-library/react'
import { NotificationProvider, useNotification } from '../NotificationContext'

function Trigger() {
  const { showWarning } = useNotification()
  return <button type="button" onClick={() => showWarning('three certificates expire', 0)}>warn</button>
}

describe('toast placement', () => {
  it('anchors the toast list to the bottom edge, centred, never to the top', async () => {
    render(<NotificationProvider><Trigger /></NotificationProvider>)
    await act(async () => { screen.getByText('warn').click() })
    const list = (await screen.findByText('three certificates expire')).closest('ol')
    const classes = list.className.split(/\s+/)
    expect(classes).toContain('fixed')
    expect(classes.some((c) => /^bottom-/.test(c))).toBe(true)
    expect(classes.some((c) => /^top-/.test(c))).toBe(false)
    expect(classes.some((c) => /^right-/.test(c))).toBe(false)
    expect(classes).toContain('left-1/2')
  })
})
