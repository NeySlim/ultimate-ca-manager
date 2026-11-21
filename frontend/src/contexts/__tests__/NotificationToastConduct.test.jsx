/**
 * What the toast kept from Radix Toast on the mockup's #toast line: its delay pauses while the pointer
 * is over it, while the focus is in it and while the window is in the background; F8 takes the focus
 * to it (and Escape gives it back); a swipe down closes it; a message shown while a modal dialog hides
 * the rest of the page is announced from inside that dialog.
 */
import { useState } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, fireEvent, render, screen, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }), initReactI18next: { type: '3rdParty', init: () => {} } }))

import { NotificationProvider, useNotification } from '../NotificationContext'
import { AtelierDialog } from '../../components/atelier/AtelierDialog'

let api
function Probe() {
  api = useNotification()
  return <button type="button">Save</button>
}

beforeEach(() => { vi.useFakeTimers({ shouldAdvanceTime: true }) })
afterEach(() => {
  cleanup()
  vi.useRealTimers()
})

const line = () => document.getElementById('toast')
const wait = (ms) => act(async () => { await vi.advanceTimersByTimeAsync(ms) })
const mount = (children = <Probe />) => render(<NotificationProvider>{children}</NotificationProvider>)

describe('toast delay: paused while the message is looked at', () => {
  it('stops counting while the pointer is over the pill and counts the rest after it leaves', async () => {
    mount()
    await act(async () => { api.showSuccess('Saved.') })
    await wait(2000)
    fireEvent.pointerMove(line(), { clientX: 10, clientY: 10 })
    await wait(10000)
    expect(line()).toHaveTextContent('Saved.')
    fireEvent.pointerLeave(line())
    await wait(2500)
    expect(line()).toHaveTextContent('Saved.')
    await wait(1000)
    expect(line()).not.toHaveClass('visible')
  })

  it('stops counting while the focus is in the message', async () => {
    mount()
    await act(async () => { api.showInfo('Exported.') })
    await act(async () => { line().focus() })
    await wait(10000)
    expect(line()).toHaveTextContent('Exported.')
    await act(async () => { screen.getByRole('button', { name: 'Save' }).focus() })
    await wait(4000)
    expect(line()).toHaveTextContent('Exported.')
    await wait(1500)
    expect(line()).not.toHaveClass('visible')
  })

  it('stops counting while the window is in the background', async () => {
    mount()
    await act(async () => { api.showSuccess('Saved.') })
    await act(async () => { window.dispatchEvent(new Event('blur')) })
    await wait(10000)
    expect(line()).toHaveTextContent('Saved.')
    await act(async () => { window.dispatchEvent(new Event('focus')) })
    await wait(5500)
    expect(line()).not.toHaveClass('visible')
  })

  it('pauses an older message still running too, and starts a new one paused', async () => {
    mount()
    await act(async () => { api.showSuccess('First.', 3000) })
    fireEvent.pointerMove(line())
    await act(async () => { api.showSuccess('Second.', 3000) })
    await wait(8000)
    expect(line()).toHaveTextContent('Second.')
    fireEvent.pointerLeave(line())
    await wait(3500)
    expect(line()).not.toHaveClass('visible')
  })
})

describe('toast: F8 takes the focus to the message', () => {
  it('focuses the line shown, and Escape there closes it and gives the focus back', async () => {
    mount()
    const save = screen.getByRole('button', { name: 'Save' })
    save.focus()
    await act(async () => { api.showSuccess('Saved.') })
    expect(line()).toHaveAttribute('aria-keyshortcuts', 'F8')
    await act(async () => { fireEvent.keyDown(save, { key: 'F8', code: 'F8' }) })
    expect(document.activeElement).toBe(line())
    await act(async () => { fireEvent.keyDown(line(), { key: 'Escape' }) })
    expect(line()).not.toHaveClass('visible')
    expect(document.activeElement).toBe(save)
  })

  it('reaches the action of a message that stays, and the focus comes back when it is closed', async () => {
    mount()
    const save = screen.getByRole('button', { name: 'Save' })
    save.focus()
    await act(async () => { api.showError('Publication failed.', { action: { label: 'Retry', onClick: () => {} } }) })
    await act(async () => { fireEvent.keyDown(save, { key: 'F8', code: 'F8' }) })
    expect(document.activeElement).toBe(line())
    const close = within(line()).getByRole('button', { name: 'common.closeMessage' })
    await act(async () => { close.focus() })
    await act(async () => { fireEvent.click(close) })
    expect(line()).not.toHaveClass('visible')
    expect(document.activeElement).toBe(save)
  })

  it('keeps the focus on the line when the message used gives way to an older one', async () => {
    mount()
    screen.getByRole('button', { name: 'Save' }).focus()
    await act(async () => { api.showError('Older failure.', 0) })
    await act(async () => { api.showError('Newer failure.', { action: { label: 'Retry', onClick: () => {} } }) })
    await act(async () => { fireEvent.keyDown(document.activeElement, { key: 'F8', code: 'F8' }) })
    const retry = within(line()).getByRole('button', { name: 'Retry' })
    await act(async () => { retry.focus() })
    await act(async () => { fireEvent.click(retry) })
    expect(line()).toHaveTextContent('Older failure.')
    expect(document.activeElement).toBe(line())
  })

  it('does nothing with no message on screen', async () => {
    mount()
    const save = screen.getByRole('button', { name: 'Save' })
    save.focus()
    await act(async () => { fireEvent.keyDown(save, { key: 'F8', code: 'F8' }) })
    expect(document.activeElement).toBe(save)
  })
})

describe('toast: a swipe down closes it', () => {
  it('follows the pointer down and closes past 50 px', async () => {
    mount()
    await act(async () => { api.showSuccess('Saved.') })
    fireEvent.pointerDown(line(), { button: 0, clientX: 100, clientY: 100, pointerType: 'mouse' })
    fireEvent.pointerMove(line(), { clientX: 101, clientY: 130, pointerType: 'mouse' })
    expect(line()).toHaveAttribute('data-swipe', 'move')
    expect(line().style.getPropertyValue('--toast-swipe-y')).toBe('30px')
    await act(async () => { fireEvent.pointerUp(line(), { clientX: 101, clientY: 170, pointerType: 'mouse' }) })
    expect(line()).not.toHaveClass('visible')
    expect(line()).not.toHaveAttribute('data-swipe')
  })

  it('comes back when released short, and the release does not press the action under it', async () => {
    mount()
    const onClick = vi.fn()
    await act(async () => { api.showError('Publication failed.', { action: { label: 'Retry', onClick } }) })
    const retry = within(line()).getByRole('button', { name: 'Retry' })
    fireEvent.pointerDown(retry, { button: 0, clientX: 100, clientY: 100, pointerType: 'mouse' })
    fireEvent.pointerMove(retry, { clientX: 100, clientY: 120, pointerType: 'mouse' })
    await act(async () => { fireEvent.pointerUp(retry, { clientX: 100, clientY: 130, pointerType: 'mouse' }) })
    fireEvent.click(retry)
    expect(onClick).not.toHaveBeenCalled()
    expect(line()).toHaveClass('visible', 'failure')
    expect(line()).not.toHaveAttribute('data-swipe')
    expect(line().style.getPropertyValue('--toast-swipe-y')).toBe('')
    fireEvent.click(retry)
    expect(onClick).toHaveBeenCalledTimes(1)
  })

  it('ignores a sideways drag and a swipe up', async () => {
    mount()
    await act(async () => { api.showSuccess('Saved.', 0) })
    fireEvent.pointerDown(line(), { button: 0, clientX: 100, clientY: 100, pointerType: 'mouse' })
    fireEvent.pointerMove(line(), { clientX: 160, clientY: 100, pointerType: 'mouse' })
    fireEvent.pointerMove(line(), { clientX: 160, clientY: 200, pointerType: 'mouse' })
    await act(async () => { fireEvent.pointerUp(line(), { clientX: 160, clientY: 200, pointerType: 'mouse' }) })
    fireEvent.pointerDown(line(), { button: 0, clientX: 100, clientY: 100, pointerType: 'mouse' })
    await act(async () => { fireEvent.pointerUp(line(), { clientX: 100, clientY: 20, pointerType: 'mouse' }) })
    expect(line()).toHaveClass('visible')
  })
})

function DialogPage() {
  api = useNotification()
  const [open, setOpen] = useState(true)
  return open ? <AtelierDialog title="Issue a certificate" onClose={() => setOpen(false)}><button type="button">Issue</button></AtelierDialog> : null
}

describe('toast: announced under a modal dialog', () => {
  it('announces a message from inside an open Atelier dialog, then removes the announcement', async () => {
    mount(<DialogPage />)
    const dialog = await screen.findByRole('dialog')
    await act(async () => { api.showError('Issuing failed.') })
    await wait(50)
    const said = within(dialog).getByRole('status')
    expect(said).toHaveTextContent('Issuing failed.')
    expect(said).toHaveAttribute('aria-live', 'assertive')
    expect(line()).toHaveTextContent('Issuing failed.')
    await wait(1100)
    expect(within(dialog).queryByRole('status')).toBeNull()
  })

  it('leaves the announcement to the line under the confirmation dialog, whose layer spares live regions', async () => {
    mount()
    await act(async () => { api.showConfirm('Revoke?') })
    const confirm = await screen.findByTestId('confirm-dialog')
    expect(screen.getByTestId('confirm-dialog').ownerDocument.body.querySelector('[aria-hidden="true"]')).not.toBeNull()
    expect(line().closest('[aria-hidden="true"]')).toBeNull()
    await act(async () => { api.showSuccess('Saved.') })
    await wait(50)
    expect(within(confirm).queryByRole('status')).toBeNull()
    expect(line()).toHaveTextContent('Saved.')
  })

  it('adds no second announcement when no dialog hides the line', async () => {
    mount()
    await act(async () => { api.showSuccess('Saved.') })
    await wait(50)
    expect(screen.getAllByText('Saved.')).toHaveLength(1)
  })
})
