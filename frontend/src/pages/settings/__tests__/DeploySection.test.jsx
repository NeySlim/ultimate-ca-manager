import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render as rtlRender, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

// The targets keep their sort in the address
const render = (ui) => rtlRender(ui, { wrapper: MemoryRouter })

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

const mobile = vi.hoisted(() => ({ isMobile: false }))
vi.mock('../../../contexts/MobileContext', () => ({ useMobile: () => mobile }))
vi.mock('../../../stores/timezoneStore', () => ({ getAppTimezone: () => 'UTC' }))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(),
    showError: vi.fn(),
    showConfirm: vi.fn(),
  }),
  useMobile: () => ({ isMobile: false, isTablet: false, isDesktop: true, isTouch: false, isLargeScreen: true, screenWidth: 1440 }),
}))

const getEffective = vi.hoisted(() => vi.fn())
vi.mock('../../../services', () => ({
  deployService: {
    getTargets: vi.fn().mockResolvedValue({ data: [] }),
  },
  policiesService: { getEffective },
}))

import DeploySection from '../DeploySection'
import { blockedWhileSuspended } from '../../../components/shell/__tests__/writeGuardProbe'

describe('DeploySection same-host preset', () => {
  it('fills the local SFTP target fields', async () => {
    render(<DeploySection />)

    fireEvent.click(await screen.findByText('deploy.addTarget'))
    fireEvent.click(screen.getByText('deploy.sameHost'))

    expect(screen.getByDisplayValue('127.0.0.1')).toBeInTheDocument()
    expect(screen.getByDisplayValue('ucm-deploy')).toBeInTheDocument()
    expect(screen.queryByText('deploy.reloadCommand')).not.toBeInTheDocument()
    expect(screen.getByText('deploy.sameHostHint')).toBeInTheDocument()
  })
})

describe('DeploySection key hint in FIPS mode (#399)', () => {
  it('announces an ECDSA P-256 key in FIPS mode', async () => {
    getEffective.mockResolvedValue({ data: { fips: true } })
    render(<DeploySection />)
    fireEvent.click(await screen.findByText('deploy.addTarget'))
    expect(await screen.findByText('deploy.privateKeyOptionalFips')).toBeInTheDocument()
    expect(screen.queryByText('deploy.privateKeyOptional')).not.toBeInTheDocument()
  })

  it('keeps the Ed25519 hint outside FIPS mode', async () => {
    getEffective.mockResolvedValue({ data: {} })
    render(<DeploySection />)
    fireEvent.click(await screen.findByText('deploy.addTarget'))
    expect(screen.getByText('deploy.privateKeyOptional')).toBeInTheDocument()
  })
})

describe('DeploySection HTTP API target (#428)', () => {
  it('swaps the SSH fields for the request fields and sends kind=http', async () => {
    const { deployService } = await import('../../../services')
    deployService.createTarget = vi.fn().mockResolvedValue({ data: { id: 7, kind: 'http' } })
    render(<DeploySection />)
    fireEvent.click(await screen.findByText('deploy.addTarget'))

    expect(screen.getByText('deploy.sshUser')).toBeInTheDocument()
    fireEvent.click(screen.getByText('deploy.kind_http'))
    expect(screen.queryByText('deploy.sshUser')).not.toBeInTheDocument()
    expect(screen.queryByText('deploy.privateKeyOptional')).not.toBeInTheDocument()
    expect(screen.getByText('deploy.httpUrl')).toBeInTheDocument()
    expect(screen.getByText('deploy.bodyTemplate')).toBeInTheDocument()
    expect(screen.getByText('deploy.allowPrivateKey')).toBeInTheDocument()

    const dialog = screen.getByRole('dialog')
    const inputs = dialog.querySelectorAll('input, textarea, select')
    const byPlaceholder = (fragment) => [...inputs].find(el => (el.placeholder || '').includes(fragment))
    fireEvent.change(screen.getByLabelText('common.name'), { target: { value: 'fw' } })
    fireEvent.change(byPlaceholder('/api/trust/cert/add'), { target: { value: 'https://fw.example.net/api/x' } })
    fireEvent.change(byPlaceholder('Authorization'), { target: { value: 'X-Api-Key: k' } })
    fireEvent.change(byPlaceholder('{{name|json}}'), { target: { value: '{"cert": {{cert_pem|json}}}' } })
    fireEvent.submit(dialog.querySelector('form'))

    await vi.waitFor(() => expect(deployService.createTarget).toHaveBeenCalled())
    const payload = deployService.createTarget.mock.calls[0][0]
    expect(payload).toMatchObject({
      kind: 'http', name: 'fw', url: 'https://fw.example.net/api/x', http_method: 'POST',
      http_headers: 'X-Api-Key: k', body_template: '{"cert": {{cert_pem|json}}}', allow_private_key: false,
    })
    expect(payload.private_key).toBeUndefined()
    expect(payload.host).toBeUndefined()
  })

  it('keeps the stored headers when the box is left empty on edit', async () => {
    const { deployService } = await import('../../../services')
    deployService.getTargets = vi.fn().mockResolvedValue({ data: [{
      id: 3, kind: 'http', name: 'fw', enabled: true, url: 'https://fw.example.net/api', http_method: 'PUT',
      http_header_names: ['Authorization'], body_template: '{}', allow_private_key: true, failure_count: 0,
    }] })
    deployService.updateTarget = vi.fn().mockResolvedValue({ data: {} })
    render(<DeploySection />)
    expect(await screen.findByText('PUT https://fw.example.net/api')).toBeInTheDocument()
    expect(screen.getByText('deploy.httpSendsKey')).toBeInTheDocument()
    expect(screen.queryByTitle('deploy.showPublicKey')).not.toBeInTheDocument()

    fireEvent.click(screen.getByTitle('common.edit'))
    const dialog = await screen.findByRole('dialog')
    expect(within(dialog).queryByText('deploy.kind_http')).not.toBeInTheDocument()  // the kind is fixed after creation
    fireEvent.submit(dialog.querySelector('form'))
    await vi.waitFor(() => expect(deployService.updateTarget).toHaveBeenCalled())
    const [id, payload] = deployService.updateTarget.mock.calls[0]
    expect(id).toBe(3)
    expect(payload.http_headers).toBeUndefined()
    expect(payload.kind).toBeUndefined()
    expect(payload).toMatchObject({ url: 'https://fw.example.net/api', http_method: 'PUT', allow_private_key: true })
  })

  it('removes the stored headers only through the explicit action', async () => {
    const { deployService } = await import('../../../services')
    deployService.getTargets = vi.fn().mockResolvedValue({ data: [{
      id: 3, kind: 'http', name: 'fw', enabled: true, url: 'https://fw.example.net/api', http_method: 'POST',
      http_header_names: ['Authorization'], body_template: '{}', allow_private_key: false, failure_count: 0,
    }] })
    deployService.updateTarget = vi.fn().mockResolvedValue({ data: {} })
    render(<DeploySection />)
    await screen.findByText('POST https://fw.example.net/api')
    fireEvent.click(screen.getByTitle('common.edit'))
    const dialog = await screen.findByRole('dialog')
    fireEvent.click(screen.getByText('common.remove'))
    expect(screen.getByText('deploy.httpHeadersRemoved')).toBeInTheDocument()
    fireEvent.click(screen.getByText('deploy.httpHeadersKeep'))  // changed my mind: stored headers stay
    expect(screen.queryByText('deploy.httpHeadersRemoved')).not.toBeInTheDocument()
    fireEvent.click(screen.getByText('common.remove'))
    fireEvent.submit(dialog.querySelector('form'))
    await vi.waitFor(() => expect(deployService.updateTarget).toHaveBeenCalled())
    expect(deployService.updateTarget.mock.calls[0][1].http_headers).toEqual({})
  })
})

describe('DeploySection write guard', () => {
  it('suspends Add a target with the other writes', async () => {
    const { deployService } = await import('../../../services')
    deployService.getTargets = vi.fn().mockResolvedValue({ data: [{ id: 3, kind: 'http', name: 'fw', enabled: true, url: 'https://fw.example.net/api', http_method: 'PUT', failure_count: 0 }] })
    render(<DeploySection />)
    await screen.findByText('PUT https://fw.example.net/api')
    expect(blockedWhileSuspended(screen.getByText('deploy.addTarget').closest('button'))).toBe(true)
  })
})

const pad = (n) => String(n).padStart(2, '0')
const rows = () => [...document.querySelectorAll('table.module-table tbody tr')]
const names = () => rows().map((tr) => tr.querySelector('th, td').textContent.trim())
const TARGETS = Array.from({ length: 27 }, (_, i) => (i % 3 === 0
  ? { id: i + 1, kind: 'http', name: `api-${pad(i + 1)}`, enabled: true, url: `https://fw${pad(i + 1)}.example.net/api`, http_method: 'PUT', failure_count: 0 }
  : { id: i + 1, kind: 'ssh', name: `host-${pad(i + 1)}`, enabled: i !== 1, host: `srv${pad(i + 1)}.example.net`, port: 22, username: 'deploy', failure_count: i === 4 ? 2 : 0 }))

describe('DeploySection targets table', () => {
  const load = async (targets) => {
    const { deployService } = await import('../../../services')
    deployService.getTargets = vi.fn().mockResolvedValue({ data: targets })
    deployService.testTarget = vi.fn().mockResolvedValue({ data: { status_code: 200 } })
    render(<DeploySection />)
    return deployService
  }

  it('pages the targets by 25 in the module table', async () => {
    await load(TARGETS)
    await screen.findByText('api-01')
    expect(document.querySelector('.record-list')).toBeNull()
    expect(rows()).toHaveLength(25)
    fireEvent.click(document.querySelector('[data-page="next"]'))
    expect(names()).toEqual(['host-26', 'host-27'])
  })

  it('finds a target by its host or address and sorts by kind', async () => {
    await load(TARGETS)
    await screen.findByText('api-01')
    fireEvent.change(document.getElementById('deploy-search'), { target: { value: 'srv14' } })
    expect(names()).toEqual(['host-14'])
    fireEvent.change(document.getElementById('deploy-search'), { target: { value: 'fw07' } })
    expect(names()).toEqual(['api-07'])
    fireEvent.change(document.getElementById('deploy-search'), { target: { value: '' } })
    fireEvent.click(document.querySelector('button[data-sort="kind"]'))
    expect(rows()[0]).toHaveTextContent('deploy.kind_http')
    fireEvent.click(document.querySelector('button[data-sort="kind"]'))
    expect(rows()[0]).toHaveTextContent('deploy.kind_ssh')
  })

  it('keeps the empty block when there is no target', async () => {
    await load([])
    expect(await screen.findByText('deploy.noTargets')).toBeInTheDocument()
    expect(document.getElementById('empty-deploy')).not.toBeNull()
    expect(document.querySelector('table.module-table')).toBeNull()
    expect(document.getElementById('deploy-search')).toBeNull()
  })

  it('tests a target from its row, the SSH key only on an SSH target', async () => {
    const service = await load(TARGETS.slice(0, 2))
    await screen.findByText('api-01')
    const [api, ssh] = rows()
    expect(within(api).queryByTitle('deploy.showPublicKey')).toBeNull()
    expect(within(ssh).getByTitle('deploy.showPublicKey')).toBeInTheDocument()
    fireEvent.click(within(api).getByTitle('deploy.testConnection'))
    await vi.waitFor(() => expect(service.testTarget).toHaveBeenCalledWith(1))
  })
})

describe('DeploySection on a phone', () => {
  it('names the date of the last success by its column', async () => {
    const { deployService } = await import('../../../services')
    deployService.getTargets.mockResolvedValueOnce({ data: [
      { id: 3, name: 'web-01', kind: 'ssh', username: 'deploy', host: 'web01.example.test', port: 22, last_success_at: '2026-11-20T10:00:00Z' },
    ] })
    mobile.isMobile = true
    try {
      render(<DeploySection />)
      const record = (await screen.findAllByRole('button', { name: 'web-01' }))[0].closest('article.mobile-record')
      const facts = [...record.querySelectorAll('.row-meta > span')].map((s) => s.textContent)
      expect(facts.some((f) => f.startsWith('deploy.lastSuccessColumn '))).toBe(true)
    } finally {
      mobile.isMobile = false
    }
  })
})
