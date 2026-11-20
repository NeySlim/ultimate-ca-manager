/**
 * Double-submit guard tests (#269)
 *
 * Issuing a certificate involves slow crypto on the backend; an unguarded
 * Issue button lets a double-click create duplicates. The handler must ignore
 * re-entrant clicks while one is in flight.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, fireEvent, waitFor, screen, act } from '@testing-library/react'
import { LABEL, choose, toReview, type } from '../certificates/__tests__/issueFormTestUtils'

vi.mock('../../services', () => ({
  templatesService: { getAll: vi.fn().mockResolvedValue({ data: [] }), getForCA: vi.fn().mockResolvedValue({ data: [] }) },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: [] }) },
}))

const t = (key) => key

async function renderIssueFormWithSlowSubmit() {
  const { IssueCertificateForm } = await import('../certificates/IssueCertificateForm')

  let releaseSubmit
  const gate = new Promise((resolve) => { releaseSubmit = resolve })
  const onSubmit = vi.fn(() => gate)

  const utils = render(
    <IssueCertificateForm
      cas={[{ id: 1, descr: 'Test CA', subject: 'CN=Test CA', has_private_key: true }]}
      onSubmit={onSubmit}
      onCancel={() => {}}
      t={t}
    />
  )
  choose(LABEL.ca, '1')
  type(LABEL.cn, 'host.example.test')
  await toReview()
  return { ...utils, onSubmit, releaseSubmit }
}

describe('IssueCertificateForm — double-submit guard (#269)', () => {
  // Rendering this form is slow enough that the default 5 s runs out when the
  // machine is busy, which made the whole suite look flaky.
  it('ignores a second click while the first is in flight', async () => {
    const { onSubmit, releaseSubmit } = await renderIssueFormWithSlowSubmit()

    const button = screen.getByTestId('issue-submit')
    fireEvent.click(button)
    fireEvent.click(button)
    fireEvent.click(button)

    expect(onSubmit).toHaveBeenCalledTimes(1)

    // Once the in-flight call settles, issuing works again
    releaseSubmit()
    await waitFor(() => expect(button).not.toBeDisabled())
    fireEvent.click(button)
    expect(onSubmit).toHaveBeenCalledTimes(2)
  }, 20000)

  // Two clicks before React renders the disabled button: only the guard stops the second
  it('ignores a second click that lands before the button is disabled', async () => {
    const { onSubmit, releaseSubmit } = await renderIssueFormWithSlowSubmit()
    const button = screen.getByTestId('issue-submit')
    act(() => { button.click(); button.click() })
    expect(onSubmit).toHaveBeenCalledTimes(1)
    releaseSubmit()
    await waitFor(() => expect(button).not.toBeDisabled())
  }, 20000)

  it('disables the Issue button while issuing', async () => {
    const { releaseSubmit } = await renderIssueFormWithSlowSubmit()
    const button = screen.getByTestId('issue-submit')
    expect(button).not.toBeDisabled()
    fireEvent.click(button)
    await waitFor(() => expect(button).toBeDisabled())
    releaseSubmit()
    await waitFor(() => expect(button).not.toBeDisabled())
  })
})
