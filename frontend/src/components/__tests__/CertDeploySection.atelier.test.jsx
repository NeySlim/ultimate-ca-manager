/**
 * CertDeploySection drawn as a section of the inspector (the mockup's section title, record rows,
 * badges and buttons), never with the former card's own styles.
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  getBindings: vi.fn(),
  getTargets: vi.fn(),
  deployNow: vi.fn(),
  deleteBinding: vi.fn(),
  showConfirm: vi.fn(),
  perms: ['read:deploy', 'write:deploy'],
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, o) => (o?.date ? `${key}|${o.date}` : key) }),
}))
vi.mock('../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showConfirm: mocks.showConfirm }),
}))
vi.mock('../../hooks', () => ({
  usePermission: () => ({ hasPermission: (p) => mocks.perms.includes(p) }),
}))
vi.mock('../../services', () => ({ deployService: mocks }))

import { CertDeploySection } from '../deploy/CertDeploySection'

const certificate = { id: 42, has_private_key: true }
const BINDINGS = [
  { id: 5, target_id: 7, target_name: 'web01', enabled: true, cert_path: '/etc/ssl/app.pem', key_path: '/etc/ssl/app.key',
    reload_command: 'systemctl reload nginx', last_delivery: { status: 'delivered', delivered_at: '2026-11-01T10:00:00Z' } },
  { id: 6, target_id: 8, target_name: 'api', enabled: false, target_kind: 'http',
    last_delivery: { status: 'failed', last_error: 'HTTP 502' } },
]
const section = () => screen.getByTestId('cert-deploy')
const row = (name) => screen.getByText(name).closest('li')

beforeEach(() => {
  vi.clearAllMocks()
  mocks.perms = ['read:deploy', 'write:deploy']
  mocks.getBindings.mockResolvedValue({ data: BINDINGS })
  mocks.getTargets.mockResolvedValue({ data: [] })
  mocks.deployNow.mockResolvedValue({})
  mocks.showConfirm.mockResolvedValue(false)
  window.history.replaceState(null, '', '/certificates?item=42')
})

describe('the deployment section of the inspector', () => {
  it('is a titled section of record rows, with no class of the former card', async () => {
    render(<CertDeploySection certificate={certificate} />)
    await screen.findByText('web01')
    expect(section().tagName).toBe('SECTION')
    expect(section().querySelector(':scope > h3.section-title')).toHaveTextContent('deploy.certSection')
    const rows = section().querySelectorAll('ul.record-list > li[data-binding-id]')
    expect([...rows].map((li) => li.dataset.bindingId)).toEqual(['5', '6'])
    expect(rows[0].querySelector('.rl-main > strong')).toHaveTextContent('web01')
    expect(rows[0].querySelector('.rl-meta .mono')).toHaveTextContent('/etc/ssl/app.pem · /etc/ssl/app.key')
    expect(rows[0].querySelector('.rl-meta')).toHaveTextContent('deploy.lastDeployed|')
    // The label carries its own colon, spaced as each language spaces it
    expect(rows[0].querySelector('.rl-meta')).toHaveTextContent('deploy.reloadCommandIs systemctl reload nginx')
    // Only the mockup's vocabulary: no Tailwind utility, no former card
    const classes = [...section().querySelectorAll('[class]')].flatMap((el) => [...el.classList])
    expect(classes.filter((c) => /^(bg-|text-|p-|space-|flex|items-|gap-|rounded|border|font-|truncate|status-)/.test(c))).toEqual([])
    expect(section().closest('.atl-out')).toBeNull()
  })

  it('says each state with the mockup badges', async () => {
    render(<CertDeploySection certificate={certificate} />)
    await screen.findByText('web01')
    expect(within(row('web01')).getByText('deploy.status.delivered').closest('.badge')).toHaveClass('good')
    expect(within(row('api')).getByText('deploy.status.failed').closest('.badge')).toHaveClass('bad')
    expect(within(row('api')).getByText('common.disabled').closest('.badge')).toHaveClass('muted')
    expect(within(row('api')).getByText('HTTP 502').closest('.rl-error')).not.toBeNull()
    expect(row('api').querySelector('.rl-meta')).toHaveTextContent('deploy.httpBinding')
  })

  it('offers its actions as the mockup buttons, each named, the detach confirmed first', async () => {
    render(<CertDeploySection certificate={certificate} />)
    await screen.findByText('web01')
    const actions = row('web01').querySelector('.rl-action')
    const deploy = within(actions).getByRole('button', { name: 'deploy.deployNow' })
    expect(deploy).toHaveClass('btn')
    expect(within(actions).getByRole('button', { name: 'common.edit' })).toHaveClass('icon-btn', 'quiet')
    fireEvent.click(within(actions).getByRole('button', { name: 'deploy.detachTarget' }))
    await waitFor(() => expect(mocks.showConfirm).toHaveBeenCalled())
    expect(mocks.deleteBinding).not.toHaveBeenCalled()
    fireEvent.click(deploy)
    await waitFor(() => expect(mocks.deployNow).toHaveBeenCalledWith(5))
    expect(within(section()).getByRole('button', { name: 'deploy.attachTarget' })).toHaveClass('btn')
  })

  it('marks the binding the work queue links to', async () => {
    window.history.replaceState(null, '', '/certificates?item=42&binding=6')
    render(<CertDeploySection certificate={certificate} />)
    await screen.findByText('web01')
    expect(row('api')).toHaveAttribute('aria-current', 'true')
    expect(row('web01')).not.toHaveAttribute('aria-current')
  })

  it('says when nothing is deployed, and a reader gets no action', async () => {
    mocks.getBindings.mockResolvedValue({ data: [] })
    render(<CertDeploySection certificate={certificate} />)
    expect(await screen.findByText('deploy.noBindings')).toHaveClass('muted', 'small')
    mocks.perms = ['read:deploy']
    mocks.getBindings.mockResolvedValue({ data: BINDINGS })
    render(<CertDeploySection certificate={{ id: 43 }} />)
    await screen.findByText('web01')
    expect(row('web01').querySelector('.rl-action')).toBeNull()
  })
})
