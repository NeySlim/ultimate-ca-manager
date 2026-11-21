/** Cloudflare creation: a token, or the legacy key with its email, as the server accepts. */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'
import { notificationSpies } from './pageRenderingSetup.jsx'

import DnsProviderForm from '../acme/DnsProviderForm'

const TYPES = [{ type: 'cloudflare', name: 'Cloudflare', description: 'Cloudflare DNS', credentials_schema: [
  { name: 'api_token', label: 'API Token', type: 'password', required: false },
  { name: 'api_key', label: 'Global API Key (legacy)', type: 'password', required: false },
  { name: 'email', label: 'Email (legacy)', type: 'text', required: false },
] }]

const fill = (label, value) => fireEvent.change(screen.getByLabelText(label), { target: { value } })

describe('Cloudflare credentials', () => {
  let onSubmit
  let container
  beforeEach(() => {
    vi.clearAllMocks()
    onSubmit = vi.fn()
    ;({ container } = render(<DnsProviderForm provider={null} providerTypes={TYPES}
                                              onSubmit={onSubmit} onCancel={() => {}} />))
    fireEvent.change(screen.getByPlaceholderText('acme.providerNamePlaceholder'), { target: { value: 'cf' } })
    fireEvent.click(screen.getByRole('button', { name: /Cloudflare/ }))
  })
  const submit = () => fireEvent.submit(container.querySelector('form'))

  it('refuses a key without its email', () => {
    fill(/Global API Key/, 'k'.repeat(37))
    submit()
    expect(onSubmit).not.toHaveBeenCalled()
    expect(notificationSpies.showWarning).toHaveBeenCalledWith('acme.credentialsEitherOr')
  })

  it('accepts a key with its email', () => {
    fill(/Global API Key/, 'k'.repeat(37))
    fill(/Email/, 'ops@example.com')
    submit()
    expect(onSubmit).toHaveBeenCalled()
  })

  it('accepts a token alone', () => {
    fill(/API Token/, 't'.repeat(40))
    submit()
    expect(onSubmit).toHaveBeenCalled()
  })
})
