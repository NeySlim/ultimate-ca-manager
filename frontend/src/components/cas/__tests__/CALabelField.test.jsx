/**
 * The display name and description of a CA (#459) in the side panel: shown to every reader,
 * edited by a writer in one dialog that sends both by PATCH and announces the change.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import en from '../../../i18n/locales/en.json'

const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), en)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => {
      const vars = typeof opts === 'object' && opts ? opts : {}
      return String(lookup(key) ?? key).replace(/\{\{(\w+)\}\}/g, (_m, name) => (vars[name] ?? `{{${name}}}`))
    },
  }),
}))
const notify = vi.hoisted(() => ({ showSuccess: vi.fn(), showError: vi.fn() }))
vi.mock('../../../contexts/NotificationContext', () => ({ useNotification: () => notify }))
const svc = vi.hoisted(() => ({ update: vi.fn() }))
vi.mock('../../../services', () => ({ casService: svc }))

import { CALabelField } from '../CALabelField'
import { Facts } from '../../atelier/Detail'

const L = en.cas.label
const base = { id: 4, name: 'Issuing CN', descr: 'Issuing CN', common_name: 'Issuing CN', description: '' }
const draw = (ca, props = {}) => render(<Facts items={[]}><CALabelField ca={ca} {...props} /></Facts>)
const valueOf = (label) => screen.getByText(label, { selector: 'dt' }).nextElementSibling
const dialog = () => screen.getByRole('dialog')

beforeEach(() => vi.clearAllMocks())

describe('the name and description of a CA', () => {
  it('shows a reader both, line breaks kept, and no editor', () => {
    draw({ ...base, name: 'Corporate Root', description: 'Line 1\nLine 2' })
    expect(valueOf(L.displayName)).toHaveTextContent('Corporate Root')
    expect(screen.getByText(/Line 1/).textContent).toBe('Line 1\nLine 2')
    expect(screen.queryByRole('button', { name: L.edit })).toBeNull()
  })

  it('says there is no description', () => {
    draw(base)
    expect(valueOf(L.description)).toHaveTextContent(L.noDescription)
  })

  it('lets a writer change both: PATCH with the trimmed name, the CA handed back, the change announced', async () => {
    const onChanged = vi.fn()
    const changed = vi.fn()
    window.addEventListener('ucm:data-changed', changed)
    const updated = { ...base, name: 'Gateway CA', descr: 'Gateway CA', description: 'VPN\nonly' }
    svc.update.mockResolvedValue({ data: updated })
    draw(base, { canWrite: true, onChanged })
    fireEvent.click(screen.getByRole('button', { name: L.edit }))
    const name = within(dialog()).getByRole('textbox', { name: L.displayName })
    expect(name).toHaveValue('Issuing CN')
    expect(name).toHaveAttribute('maxLength', '255')
    expect(within(dialog()).getByText(/Issuing CN\)/)).toBeInTheDocument()
    fireEvent.change(name, { target: { value: '  Gateway CA ' } })
    fireEvent.change(within(dialog()).getByRole('textbox', { name: L.description }), { target: { value: 'VPN\nonly' } })
    expect(within(dialog()).getByText('8 / 1000', { exact: false })).toBeInTheDocument()
    fireEvent.click(within(dialog()).getByRole('button', { name: en.common.save }))
    await waitFor(() => expect(onChanged).toHaveBeenCalledWith(updated))
    expect(svc.update).toHaveBeenCalledWith(4, { name: 'Gateway CA', description: 'VPN\nonly' })
    expect(notify.showSuccess).toHaveBeenCalledWith(L.saved)
    expect(changed.mock.calls[0][0].detail).toEqual({ type: 'ca' })
    expect(screen.queryByRole('dialog')).toBeNull()
    window.removeEventListener('ucm:data-changed', changed)
  })

  it('refuses an empty name without calling the server', () => {
    draw(base, { canWrite: true })
    fireEvent.click(screen.getByRole('button', { name: L.edit }))
    fireEvent.change(within(dialog()).getByRole('textbox', { name: L.displayName }), { target: { value: '   ' } })
    fireEvent.click(within(dialog()).getByRole('button', { name: en.common.save }))
    expect(within(dialog()).getByText(L.nameRequired)).toBeInTheDocument()
    expect(svc.update).not.toHaveBeenCalled()
  })

  it('keeps the dialog open with the server message when the save is refused', async () => {
    svc.update.mockRejectedValue(new Error('name must be 255 characters or fewer'))
    draw(base, { canWrite: true })
    fireEvent.click(screen.getByRole('button', { name: L.edit }))
    fireEvent.click(within(dialog()).getByRole('button', { name: en.common.save }))
    expect(await within(dialog()).findByText('name must be 255 characters or fewer')).toBeInTheDocument()
  })
})
