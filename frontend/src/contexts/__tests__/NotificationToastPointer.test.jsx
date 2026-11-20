/**
 * A passing toast lets the pointer through to what lies under it, its viewport included (the
 * viewport spans the toasts it stacks); a toast that stays keeps its buttons clickable.
 */
import fs from 'fs'
import path from 'path'
import { afterEach, beforeAll, describe, expect, it } from 'vitest'
import { act, cleanup, render, screen } from '@testing-library/react'

import { NotificationProvider, useNotification } from '../NotificationContext'

beforeAll(() => {
  global.ResizeObserver = class ResizeObserver { observe() {} unobserve() {} disconnect() {} }
  const style = document.createElement('style')
  style.textContent = fs.readFileSync(path.resolve(__dirname, '../../styles/primitives.css'), 'utf8')
  document.head.appendChild(style)
})
afterEach(cleanup)

let api
function Probe() {
  api = useNotification()
  return null
}

const pointer = (el) => getComputedStyle(el).pointerEvents

describe('toast viewport and the pointer', () => {
  it('lets the pointer through the viewport and a passing toast', async () => {
    render(<NotificationProvider><Probe /></NotificationProvider>)
    await act(async () => { api.showSuccess('CA created: Lab root') })
    const toast = screen.getByText('CA created: Lab root').closest('li')
    expect(pointer(toast.closest('.ui-toast-viewport'))).toBe('none')
    expect(pointer(toast)).toBe('none')
  })

  it('keeps a toast that stays clickable', async () => {
    render(<NotificationProvider><Probe /></NotificationProvider>)
    await act(async () => { api.showError('Publication failed.', { action: { label: 'Retry', onClick: () => {} } }) })
    expect(pointer(screen.getByText('Publication failed.').closest('li'))).toBe('auto')
  })
})
