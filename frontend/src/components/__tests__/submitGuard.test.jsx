/**
 * Double-submit guard of the shared Button (DUP-FE-015).
 *
 * `Button` spread `{...props}` AFTER computing `disabled={loading || props.disabled}`,
 * so any caller passing BOTH `loading` and an explicit `disabled` had the computed
 * value overwritten by its own prop. Five modals do exactly that
 * (UploadCACertModal, UploadCRLModal, RestoreModal, TakeOfflineModal,
 * CertDeploySection): while the request was in flight their submit button stayed
 * enabled, so Enter or a keyboard activation fired the action a second time.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { Button } from '../Button'

describe('Button — loading is a real guard, not just a spinner', () => {
  it('stays disabled while loading even when the caller passes disabled={false}', () => {
    render(<Button loading disabled={false}>Save</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('ignores a click while loading, with an explicit disabled={false}', () => {
    const onClick = vi.fn()
    render(<Button type="button" loading disabled={false} onClick={onClick}>Save</Button>)
    fireEvent.click(screen.getByRole('button'))
    expect(onClick).not.toHaveBeenCalled()
  })

  it('still honours an explicit disabled={true} when not loading', () => {
    render(<Button disabled>Save</Button>)
    expect(screen.getByRole('button')).toBeDisabled()
  })

  it('is enabled when neither loading nor disabled', () => {
    render(<Button>Save</Button>)
    expect(screen.getByRole('button')).not.toBeDisabled()
  })
})
