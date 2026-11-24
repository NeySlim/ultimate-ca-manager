/**
 * The comment of a certificate in the dock's Aperçu (#454): plain text to every reader, edited in
 * a dialog by a writer (multiline field, counter, Save and Cancel), saved alone by PATCH.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import en from '../../../i18n/locales/en.json'

const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), en)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => {
      const vars = typeof opts === 'object' && opts ? opts : {}
      const template = lookup(key) ?? (typeof opts === 'string' ? opts : key)
      return String(template).replace(/\{\{(\w+)\}\}/g, (_m, name) => (vars[name] ?? `{{${name}}}`))
    },
  }),
}))
const perms = vi.hoisted(() => ({ granted: [] }))
vi.mock('../../../hooks', () => ({ usePermission: () => ({ hasPermission: (p) => perms.granted.includes(p) }) }))
const notify = vi.hoisted(() => ({ showSuccess: vi.fn(), showError: vi.fn() }))
vi.mock('../../../contexts/NotificationContext', () => ({ useNotification: () => notify }))
const svc = vi.hoisted(() => ({ updateComment: vi.fn() }))
vi.mock('../../../services/certificates.service', () => ({ certificatesService: svc }))
vi.mock('../../../services/acme.service', () => ({ acmeService: { getClientOrders: vi.fn() } }))
vi.mock('../../../components/deploy/CertDeploySection', () => ({ CertDeploySection: () => <section data-testid="cert-deploy" /> }))

import { OverviewPanel } from '../inspector/OverviewPanel'

const C = en.certificates
const base = {
  id: 7, common_name: 'pc.example.com', subject: 'CN=pc.example.com', serial_number: '42',
  valid_to: '2030-01-01T00:00:00Z', status: 'valid',
}
const ident = () => screen.getByText(en.inspector.cert.identity).closest('section')
const value = () => within(ident()).getByText(C.comment).nextElementSibling
const dialog = () => screen.getByRole('dialog', { name: C.editComment })
const field = () => within(dialog()).getByRole('textbox', { name: C.comment })

beforeEach(() => {
  perms.granted = []
  vi.clearAllMocks()
})

describe('the comment of a certificate in Aperçu', () => {
  it('shows a reader the text as written, markup and line breaks included, and no editor', () => {
    perms.granted = ['read:certificates']
    render(<OverviewPanel cert={{ ...base, comment: 'Rack 12\n<b>owner</b> ops' }} title="pc" />)
    expect(value().textContent).toBe('Rack 12\n<b>owner</b> ops')
    expect(value().querySelector('b')).toBeNull()
    expect(screen.queryByRole('button', { name: C.editComment })).toBeNull()
    expect(screen.queryByRole('button', { name: C.addComment })).toBeNull()
  })

  it('says there is none', () => {
    render(<OverviewPanel cert={{ ...base, comment: '' }} title="pc" />)
    expect(value()).toHaveTextContent(en.inspector.cert.none)
  })

  it('lets a writer add one: the counter follows the text, Save sends it and hands the certificate back', async () => {
    perms.granted = ['write:certificates']
    const onChanged = vi.fn()
    const changed = vi.fn()
    window.addEventListener('ucm:data-changed', changed)
    svc.updateComment.mockResolvedValue({ data: { ...base, comment: 'Line 1\nLine 2' } })
    render(<OverviewPanel cert={{ ...base, comment: '' }} title="pc" onChanged={onChanged} />)
    fireEvent.click(screen.getByRole('button', { name: C.addComment }))
    expect(field()).toHaveValue('')
    expect(field()).toHaveAttribute('maxLength', '4000')
    expect(within(dialog()).getByText('0 / 4000', { exact: false })).toBeInTheDocument()
    fireEvent.change(field(), { target: { value: 'Line 1\nLine 2' } })
    expect(within(dialog()).getByText('13 / 4000', { exact: false })).toBeInTheDocument()
    fireEvent.click(within(dialog()).getByRole('button', { name: en.common.save }))
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ id: 7, comment: 'Line 1\nLine 2' })))
    expect(svc.updateComment).toHaveBeenCalledWith(7, 'Line 1\nLine 2')
    expect(notify.showSuccess).toHaveBeenCalledWith(C.commentSaved)
    expect(changed).toHaveBeenCalled()
    expect(screen.queryByRole('dialog')).toBeNull()
    window.removeEventListener('ucm:data-changed', changed)
  })

  it('lets a writer clear one, and Cancel sends nothing', async () => {
    perms.granted = ['write:certificates']
    svc.updateComment.mockResolvedValue({ data: { ...base, comment: '' } })
    render(<OverviewPanel cert={{ ...base, comment: 'Old' }} title="pc" onChanged={vi.fn()} />)
    fireEvent.click(screen.getByRole('button', { name: C.editComment }))
    expect(field()).toHaveValue('Old')
    fireEvent.click(within(dialog()).getByRole('button', { name: en.common.cancel }))
    expect(screen.queryByRole('dialog')).toBeNull()
    expect(svc.updateComment).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: C.editComment }))
    fireEvent.change(field(), { target: { value: '' } })
    fireEvent.click(within(dialog()).getByRole('button', { name: en.common.save }))
    await waitFor(() => expect(svc.updateComment).toHaveBeenCalledWith(7, ''))
  })

  it('keeps the text and says why when the save fails', async () => {
    perms.granted = ['write:certificates']
    const onChanged = vi.fn()
    svc.updateComment.mockRejectedValue(new Error('comment must be 4000 characters or fewer'))
    render(<OverviewPanel cert={{ ...base, comment: 'Old' }} title="pc" onChanged={onChanged} />)
    fireEvent.click(screen.getByRole('button', { name: C.editComment }))
    fireEvent.change(field(), { target: { value: 'New text' } })
    fireEvent.click(within(dialog()).getByRole('button', { name: en.common.save }))
    expect(await within(dialog()).findByRole('alert')).toHaveTextContent('comment must be 4000 characters or fewer')
    expect(field()).toHaveValue('New text')
    expect(onChanged).not.toHaveBeenCalled()
  })
})
