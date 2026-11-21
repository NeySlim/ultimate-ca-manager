/** Central write guard: every write control of the page, inspector and dialogs waits while writes are suspended. */
import { describe, it, expect, vi, afterEach } from 'vitest'
import { render, screen, act, fireEvent } from '@testing-library/react'
import { useState } from 'react'
import { useCentralWriteGuard, applyWriteGuard } from '../writeGuard'

const NOTE = 'shell-writes-note'
const SUSPENDED = { suspended: true, noteId: NOTE }
const RUNNING = { suspended: false }

// A page as the shell holds it, a dialog portalled to the body, and the top bar outside both
function Page({ busy = false, onIssue = () => {}, onRead = () => {}, onSubmit = (e) => e.preventDefault() }) {
  return (
    <>
      <header className="shell-topbar"><button type="button" className="shell-btn is-primary">bar</button></header>
      <div className="shell-main">
        <button type="button" className="lv-btn is-primary" onClick={onIssue} disabled={busy}>Issue</button>
        <button type="button" className="lv-btn is-quiet" data-write>Import</button>
        <button type="button" className="lv-btn is-quiet">Filter</button>
        <button type="button" className="lv-btn is-primary" data-write="false" onClick={onRead}>Retry</button>
        <button type="button" className="btn-gradient danger">Delete</button>
        <a className="lv-btn is-primary" href="/certificates?action=create" onClick={onIssue}>Issue page</a>
        <form onSubmit={onSubmit}><input aria-label="name" /><button type="submit">Save</button></form>
        <button type="button" className="lv-btn is-primary" disabled>Own reason</button>
      </div>
      <div role="dialog"><button type="button" className="wk-btn is-primary">Publish</button></div>
    </>
  )
}

function Shell({ guard, ...page }) {
  useCentralWriteGuard(guard)
  return <Page {...page} />
}

afterEach(() => { document.body.innerHTML = '' })

describe('applyWriteGuard', () => {
  it('disables the write controls of the page, the inspector and the dialogs, pointing to the reason', () => {
    render(<Page />)
    applyWriteGuard(SUSPENDED)
    for (const name of ['Issue', 'Import', 'Delete', 'Save', 'Publish']) {
      const el = screen.getByRole('button', { name })
      expect(el).toBeDisabled()
      expect(el).toHaveAttribute('aria-describedby', NOTE)
    }
    const link = screen.getByRole('link', { name: 'Issue page' })
    expect(link).toHaveAttribute('aria-disabled', 'true')
    expect(link).toHaveAttribute('aria-describedby', NOTE)
  })

  it('leaves alone what only reads, what opts out, and the shell bars', () => {
    render(<Page />)
    applyWriteGuard(SUSPENDED)
    for (const name of ['Filter', 'Retry', 'bar']) expect(screen.getByRole('button', { name })).toBeEnabled()
  })

  it('gives back only what it disabled, never a control disabled by its own view', () => {
    render(<Page />)
    applyWriteGuard(SUSPENDED)
    applyWriteGuard(RUNNING)
    expect(screen.getByRole('button', { name: 'Issue' })).toBeEnabled()
    expect(screen.getByRole('button', { name: 'Issue' })).not.toHaveAttribute('aria-describedby')
    expect(screen.getByRole('link', { name: 'Issue page' })).not.toHaveAttribute('aria-disabled')
    expect(screen.getByRole('button', { name: 'Own reason' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'Own reason' })).not.toHaveAttribute('aria-describedby')
  })

  it('moves the controls to the new reason when it changes (offline, then maintenance)', () => {
    render(<Page />)
    applyWriteGuard({ suspended: true, noteId: 'shell-offline-note' })
    applyWriteGuard(SUSPENDED)
    expect(screen.getByRole('button', { name: 'Issue' })).toHaveAttribute('aria-describedby', NOTE)
  })
})

describe('useCentralWriteGuard', () => {
  it('guards what renders later: a dialog opened during the suspension', async () => {
    function Late({ guard }) {
      useCentralWriteGuard(guard)
      const [open, setOpen] = useState(false)
      return (
        <div className="shell-main">
          <button type="button" onClick={() => setOpen(true)}>open</button>
          {open && <div role="dialog"><button type="submit" form="x">Confirm</button></div>}
        </div>
      )
    }
    render(<Late guard={SUSPENDED} />)
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'open' })) })
    await act(async () => {})
    expect(screen.getByRole('button', { name: 'Confirm' })).toBeDisabled()
  })

  it('takes a control back when a re-render enables it, and frees everything when writes resume', async () => {
    const { rerender } = render(<Shell guard={SUSPENDED} busy />)
    // Disabled by its view (busy) when the guard ran: left alone, then enabled by React
    rerender(<Shell guard={SUSPENDED} busy={false} />)
    await act(async () => {})
    expect(screen.getByRole('button', { name: 'Issue' })).toBeDisabled()
    rerender(<Shell guard={RUNNING} busy={false} />)
    expect(screen.getByRole('button', { name: 'Issue' })).toBeEnabled()
    expect(document.querySelectorAll('[data-write-blocked]')).toHaveLength(0)
  })

  it('takes a control it already holds back when its view enables it again', async () => {
    const { rerender } = render(<Shell guard={SUSPENDED} busy={false} />)
    const issue = () => screen.getByRole('button', { name: 'Issue' })
    expect(issue()).toBeDisabled()
    // The view goes busy then idle: React writes disabled=false over the guard's mark
    rerender(<Shell guard={SUSPENDED} busy />)
    rerender(<Shell guard={SUSPENDED} busy={false} />)
    await act(async () => {})
    expect(issue()).toBeDisabled()
    expect(issue()).toHaveAttribute('aria-describedby', NOTE)
  })

  it('stops a blocked link and a blocked form before the page sees them', async () => {
    const onIssue = vi.fn()
    const onSubmit = vi.fn((e) => e.preventDefault())
    render(<Shell guard={SUSPENDED} onIssue={onIssue} onSubmit={onSubmit} />)
    fireEvent.click(screen.getByRole('link', { name: 'Issue page' }))
    expect(onIssue).not.toHaveBeenCalled()
    const save = screen.getByRole('button', { name: 'Save' })
    fireEvent.submit(save.form)
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('lets everything through while writes run', () => {
    const onIssue = vi.fn()
    render(<Shell guard={RUNNING} onIssue={onIssue} />)
    fireEvent.click(screen.getByRole('link', { name: 'Issue page' }))
    expect(onIssue).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('button', { name: 'Issue' })).toBeEnabled()
  })
})
