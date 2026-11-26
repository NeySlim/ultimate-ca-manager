/**
 * The email template editor in the mockup's wide modal(): the format in a segmented switch, the
 * variables of the format, the source beside its live preview, Reset (custom only) and Save.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, within, fireEvent, act } from '@testing-library/react'

const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), patch: vi.fn() }))
const note = vi.hoisted(() => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: vi.fn() }))

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => key }) }))
vi.mock('../../../services/apiClient', () => ({ apiClient: api }))
vi.mock('../../../contexts/NotificationContext', () => ({ useNotification: () => note }))

import EmailTemplateDialog from '../EmailTemplateDialog'

const loaded = (custom = false) => ({
  data: {
    template: '<p>{{content}}</p>', text_template: 'TEXT {{content}}',
    default_template: '<p>default</p>', default_text_template: 'default text',
    is_custom: custom, is_text_custom: false,
  },
})

async function open(custom = false, props = {}) {
  api.get.mockResolvedValue(loaded(custom))
  api.post.mockImplementation((url, body) => Promise.resolve({ data: body?.type === 'text' ? { text: `PREVIEW ${body.template}` } : { html: `<b>${body?.template}</b>` } }))
  const onClose = vi.fn()
  render(<EmailTemplateDialog onClose={onClose} {...props} />)
  await act(async () => { await Promise.resolve(); await Promise.resolve() })
  return { onClose, dialog: screen.getByTestId('email-template-dialog') }
}

describe('EmailTemplateDialog', () => {
  beforeEach(() => { vi.clearAllMocks(); vi.useRealTimers() })

  it('shows the template read-only without admin:settings, as the API refuses the change', async () => {
    const { dialog } = await open(true, { locked: true })
    expect(within(dialog).getByLabelText('settings.templateHtmlSource')).toHaveAttribute('readonly')
    expect(within(dialog).queryByRole('button', { name: 'common.save' })).toBeNull()
    expect(within(dialog).queryByRole('button', { name: 'settings.templateResetDefault' })).toBeNull()
    expect(dialog).toHaveTextContent('settings.templateAdminOnly')
  })

  it('is the mockup\'s wide dialog with the template\'s state, not a floating window', async () => {
    const { dialog } = await open()
    expect(dialog.tagName).toBe('DIALOG')
    expect(dialog).toHaveClass('wide')
    expect(within(dialog).getByRole('heading', { level: 2 })).toHaveTextContent('settings.emailTemplate')
    expect(dialog.querySelector('.modal-head p')).toHaveTextContent('settings.templateDefault')
    expect(document.querySelector('.fixed')).toBeNull()
  })

  it('switches between the HTML and the plain text template, each with its variables and its preview', async () => {
    const { dialog } = await open()
    const group = within(dialog).getByRole('group', { name: 'settings.templateFormat' })
    expect(group).toHaveClass('segmented')
    const [html, text] = within(group).getAllByRole('button')
    expect(html).toHaveAttribute('aria-pressed', 'true')
    expect(within(dialog).getByLabelText('settings.templateHtmlSource')).toHaveValue('<p>{{content}}</p>')
    expect(dialog.querySelector('.notice')).toHaveTextContent('{{logo}}')
    expect(dialog.querySelector('iframe').getAttribute('srcdoc')).toBe('<b><p>{{content}}</p></b>')
    expect(dialog.querySelector('iframe').getAttribute('sandbox')).toBe('')
    fireEvent.click(text)
    expect(text).toHaveAttribute('aria-pressed', 'true')
    expect(within(dialog).getByLabelText('settings.templatePlainText')).toHaveValue('TEXT {{content}}')
    expect(dialog.querySelector('.notice')).not.toHaveTextContent('{{logo}}')
    expect(dialog.querySelector('.notice')).toHaveTextContent('{{instance_url}}')
    expect(dialog.querySelector('pre.code-preview')).toHaveTextContent('PREVIEW TEXT {{content}}')
  })

  it('refreshes the preview as the source changes and saves both templates', async () => {
    vi.useFakeTimers()
    const { dialog } = await open()
    const save = within(dialog).getByRole('button', { name: 'common.save' })
    expect(save).toBeDisabled()
    fireEvent.change(within(dialog).getByLabelText('settings.templateHtmlSource'), { target: { value: '<i>new</i>' } })
    await act(async () => { vi.advanceTimersByTime(800) })
    await act(async () => { await Promise.resolve() })
    expect(dialog.querySelector('iframe').getAttribute('srcdoc')).toBe('<b><i>new</i></b>')
    expect(save).toBeEnabled()
    api.patch.mockResolvedValue({})
    await act(async () => { fireEvent.click(save) })
    expect(api.patch).toHaveBeenCalledWith('/settings/email/template', { template: '<i>new</i>', text_template: 'TEXT {{content}}' })
    expect(note.showSuccess).toHaveBeenCalledWith('settings.templateSaved')
    expect(dialog.querySelector('.modal-head p')).toHaveTextContent('settings.templateCustom')
  })

  it('offers Reset only for a custom template, and restores the defaults after the confirmation', async () => {
    const { dialog } = await open(true)
    note.showConfirm.mockResolvedValue(true)
    await act(async () => { fireEvent.click(within(dialog).getByRole('button', { name: 'settings.templateResetDefault' })) })
    expect(api.post).toHaveBeenCalledWith('/settings/email/template/reset')
    expect(within(dialog).getByLabelText('settings.templateHtmlSource')).toHaveValue('<p>default</p>')
    expect(within(dialog).queryByRole('button', { name: 'settings.templateResetDefault' })).toBeNull()
  })

  it('closes from its foot, and its writes wait with the others (data-write)', async () => {
    const { dialog, onClose } = await open(true)
    expect(within(dialog).getByRole('button', { name: 'common.save' })).toHaveAttribute('data-write', '')
    expect(within(dialog).getByRole('button', { name: 'settings.templateResetDefault' })).toHaveAttribute('data-write', '')
    fireEvent.click(within(dialog.querySelector('.modal-actions')).getByRole('button', { name: 'common.close' }))
    expect(onClose).toHaveBeenCalled()
  })
})
