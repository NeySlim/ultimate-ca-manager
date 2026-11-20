/** #437: the issue form sends the custom extensions typed in, and refuses invalid ones. */
import { describe, it, expect, vi, beforeAll, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react'
import { IssueCertificateForm } from '../certificates/IssueCertificateForm'
import { LABEL, P, choose, openAdvanced, reviewAndIssue, toReview, type } from '../certificates/__tests__/issueFormTestUtils'

vi.mock('../../services', () => ({
  templatesService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getForCA: vi.fn().mockResolvedValue({ data: [] }),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))

beforeAll(() => {
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
})
afterEach(cleanup)

const t = (key) => key

async function renderForm(onSubmit) {
  const view = render(
    <IssueCertificateForm cas={[{ id: 1, descr: 'Test CA', subject: 'CN=Test CA', has_private_key: true }]}
      onSubmit={onSubmit} onCancel={() => {}} t={t} />)
  choose(LABEL.ca, '1')
  type(LABEL.cn, 'host.example.test')
  openAdvanced()
  fireEvent.click(screen.getByText('customExtensions.add'))
  return view
}

describe('IssueCertificateForm custom extensions', () => {
  it('sends them normalised', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    await renderForm(onSubmit)
    type(`${P}extOid`, '1.3.6.1.4.1.99999.7')
    type(`${P}extValue`, '05 00')
    fireEvent.click(screen.getByLabelText('customExtensions.critical'))
    expect(screen.getByTestId('custom-extensions-critical-warning')).toBeTruthy()
    const body = await reviewAndIssue(onSubmit)
    expect(body.custom_extensions).toEqual([{ oid: '1.3.6.1.4.1.99999.7', critical: true, value: '0500' }])
  })

  it('refuses an invalid entry in its row, before the Review step', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    await renderForm(onSubmit)
    type(`${P}extOid`, '1.3.6.1.4.1.99999.7')
    type(`${P}extValue`, '050')
    fireEvent.click(screen.getByRole('button', { name: new RegExp(`${P}toReview`) }))
    expect(await screen.findByText('customExtensions.invalidHex')).toBeTruthy()
    // A wrong value is marked on the value, its OID being right
    expect(screen.getByLabelText(`${P}extValue`).getAttribute('aria-invalid')).toBe('true')
    expect(screen.getByLabelText(`${P}extOid`).getAttribute('aria-invalid')).toBeNull()
    expect(screen.queryByTestId('issue-review')).toBeNull()
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('sends none when the list is empty', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    await renderForm(onSubmit)
    fireEvent.click(screen.getByRole('button', { name: `${P}removeExt` }))
    await toReview()
    fireEvent.click(screen.getByTestId('issue-submit'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0][0]).not.toHaveProperty('custom_extensions')
  })
})
