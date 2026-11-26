/**
 * OPNsense import: the API key and secret never reach browser storage. The tab keeps the
 * connection (host, port, TLS check); the credentials stay in memory and go at sign-out.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'

import OperationsPage from '../OperationsPage'
import { opnsenseService } from '../../services/opnsense.service'
import { signOutDrafts } from '../../lib/draftMemory'

const HOST = 'importExport.opnsense.hostPlaceholder'
const KEY = 'importExport.opnsense.apiKeyLabel'
const SECRET = 'importExport.opnsense.apiSecretLabel'

const mount = () => render(<MemoryRouter initialEntries={['/operations']}><OperationsPage /></MemoryRouter>)

const storedText = () => Object.keys(sessionStorage).map((k) => `${k}=${sessionStorage.getItem(k)}`).join('\n')

async function testConnection() {
  const view = mount()
  fireEvent.change(screen.getByPlaceholderText(HOST), { target: { value: '192.0.2.10' } })
  fireEvent.change(screen.getByLabelText(KEY), { target: { value: 'KEY-A' } })
  fireEvent.change(screen.getByLabelText(SECRET), { target: { value: 'SECRET-A' } })
  fireEvent.click(screen.getByText('common.testConnection'))
  await waitFor(() => expect(opnsenseService.test).toHaveBeenCalledTimes(1))
  await waitFor(() => expect(storedText()).toContain('192.0.2.10'))
  return view
}

describe('OperationsPage: OPNsense credentials stay out of browser storage', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
    signOutDrafts()
  })

  it('keeps the host but neither the API key nor the secret after a test', async () => {
    await testConnection()
    expect(storedText()).not.toContain('KEY-A')
    expect(storedText()).not.toContain('SECRET-A')
    expect(storedText()).not.toMatch(/api_(key|secret)/)
  })

  it('finds the credentials again in the same session, and loses them at sign-out', async () => {
    const view = await testConnection()
    view.unmount()
    const again = mount()
    expect(screen.getByPlaceholderText(HOST)).toHaveValue('192.0.2.10')
    expect(screen.getByLabelText(KEY)).toHaveValue('KEY-A')
    expect(screen.getByLabelText(SECRET)).toHaveValue('SECRET-A')
    again.unmount()
    signOutDrafts()
    mount()
    expect(screen.getByPlaceholderText(HOST)).toHaveValue('192.0.2.10')
    expect(screen.getByLabelText(KEY)).toHaveValue('')
    expect(screen.getByLabelText(SECRET)).toHaveValue('')
  })

  it('removes the former entry that held the secrets, keeping its connection only', () => {
    sessionStorage.setItem('opnsense_config', JSON.stringify({
      host: 'fw.example.test', port: '8443', api_key: 'OLD-KEY', api_secret: 'OLD-SECRET', verify_ssl: true,
    }))
    mount()
    expect(sessionStorage.getItem('opnsense_config')).toBeNull()
    expect(storedText()).not.toContain('OLD-')
    expect(screen.getByPlaceholderText(HOST)).toHaveValue('fw.example.test')
    expect(screen.getByLabelText(KEY)).toHaveValue('')
    expect(screen.getByLabelText(SECRET)).toHaveValue('')
  })
})
