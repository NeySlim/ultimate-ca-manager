/** #437: the issue form sends the custom extensions typed in, and refuses invalid ones. */
import { describe, it, expect, vi, beforeAll, afterEach } from 'vitest'
import { render, screen, waitFor, fireEvent, cleanup } from '@testing-library/react'
import { IssueCertificateForm } from '../certificates/IssueCertificateForm'

const showError = vi.fn()
vi.mock('../../services', () => ({
  templatesService: {
    getAll: vi.fn().mockResolvedValue({ data: [] }),
    getForCA: vi.fn().mockResolvedValue({ data: [] }),
  },
  ekuService: { getKnown: vi.fn().mockResolvedValue({ data: { ekus: [] } }) },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showError, showSuccess: vi.fn(), showWarning: vi.fn() }),
}))

beforeAll(() => {
  global.ResizeObserver = class { observe() {} unobserve() {} disconnect() {} }
})
afterEach(cleanup)

const t = (key) => key

async function renderForm(onSubmit) {
  const view = render(
    <IssueCertificateForm cas={[{ id: 1, descr: 'Test CA', subject: 'CN=Test CA' }]}
      onSubmit={onSubmit} onCancel={() => {}} t={t} />)
  fireEvent.change(screen.getByPlaceholderText('example.com'), { target: { value: 'host.example.test' } })
  fireEvent.click(screen.getByRole('button', { name: /customExtensions.title/ }))
  fireEvent.click(screen.getByText('customExtensions.add'))
  return view
}

describe('IssueCertificateForm custom extensions', () => {
  it('sends them normalised', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const { container } = await renderForm(onSubmit)
    fireEvent.change(screen.getByPlaceholderText('1.3.6.1.4.1.99999.1'), { target: { value: '1.3.6.1.4.1.99999.7' } })
    fireEvent.change(screen.getByPlaceholderText('0c0568656c6c6f'), { target: { value: '05 00' } })
    fireEvent.click(screen.getByLabelText('customExtensions.critical'))
    fireEvent.click(container.querySelector('button[type="submit"]'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0][0].custom_extensions).toEqual(
      [{ oid: '1.3.6.1.4.1.99999.7', critical: true, value: '0500' }])
  })

  it('refuses an invalid entry before submitting', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const { container } = await renderForm(onSubmit)
    fireEvent.change(screen.getByPlaceholderText('1.3.6.1.4.1.99999.1'), { target: { value: '1.3.6.1.4.1.99999.7' } })
    fireEvent.change(screen.getByPlaceholderText('0c0568656c6c6f'), { target: { value: '050' } })
    fireEvent.click(container.querySelector('button[type="submit"]'))
    await waitFor(() => expect(showError).toHaveBeenCalledWith('customExtensions.fixErrors'))
    expect(onSubmit).not.toHaveBeenCalled()
  })

  it('sends none when the list is empty', async () => {
    const onSubmit = vi.fn().mockResolvedValue(undefined)
    const { container } = await renderForm(onSubmit)
    fireEvent.click(container.querySelector('button[type="submit"]'))
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit.mock.calls[0][0]).not.toHaveProperty('custom_extensions')
  })
})
