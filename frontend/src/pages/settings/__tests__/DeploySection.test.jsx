import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({
    showSuccess: vi.fn(),
    showError: vi.fn(),
    showConfirm: vi.fn(),
  }),
}))

const getEffective = vi.hoisted(() => vi.fn())
vi.mock('../../../services', () => ({
  deployService: {
    getTargets: vi.fn().mockResolvedValue({ data: [] }),
  },
  policiesService: { getEffective },
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Badge: ({ children }) => <span>{children}</span>,
  HelpCard: ({ children }) => <div>{children}</div>,
  DetailSection: ({ children }) => <section>{children}</section>,
  DetailContent: ({ children }) => <div>{children}</div>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  EmptyState: ({ action }) => <button onClick={action.onClick}>{action.label}</button>,
}))

vi.mock('../../../components/Modal', () => ({
  Modal: ({ open, children }) => open ? <div role="dialog">{children}</div> : null,
}))

import DeploySection from '../DeploySection'

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
    fireEvent.change(inputs[0], { target: { value: 'fw' } })
    fireEvent.change(byPlaceholder('/api/trust/cert/add'), { target: { value: 'https://fw.example.net/api/x' } })
    fireEvent.change(byPlaceholder('Authorization'), { target: { value: 'X-Api-Key: k' } })
    fireEvent.change(byPlaceholder('{{name}}'), { target: { value: '{"cert": {{cert_pem|json}}}' } })
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

    const buttons = screen.getAllByRole('button')
    fireEvent.click(buttons.find(b => b.textContent === '' && !b.title) || buttons[2])
    const dialog = await screen.findByRole('dialog')
    expect(screen.queryByText('deploy.kind_http')).not.toBeInTheDocument()  // the kind is fixed after creation
    fireEvent.submit(dialog.querySelector('form'))
    await vi.waitFor(() => expect(deployService.updateTarget).toHaveBeenCalled())
    const [id, payload] = deployService.updateTarget.mock.calls[0]
    expect(id).toBe(3)
    expect(payload.http_headers).toBeUndefined()
    expect(payload.kind).toBeUndefined()
    expect(payload).toMatchObject({ url: 'https://fw.example.net/api', http_method: 'PUT', allow_private_key: true })
  })
})
