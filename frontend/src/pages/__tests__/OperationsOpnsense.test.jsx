/**
 * Regression tests for the OPNsense import form's TLS-verification default.
 *
 * PR #248 flipped the BACKEND default to verify_ssl=true, but this form
 * always sends the key explicitly, so its useState(false) default silently
 * kept the interactive path insecure: the "Ignore SSL certificate" checkbox
 * rendered CHECKED on first load and every test/import request carried
 * verify_ssl: false. These tests pin the UI to the secure default.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'

import OperationsPage from '../OperationsPage'
import { opnsenseService } from '../../services/opnsense.service'

function renderOperations() {
  return render(
    <MemoryRouter initialEntries={['/operations']}>
      <OperationsPage />
    </MemoryRouter>
  )
}

// With react-i18next mocked (t => key), labels/placeholders render as keys.
const IGNORE_CERT_LABEL = 'importExport.opnsense.ignoreCert'

function getIgnoreCertCheckbox() {
  const label = screen.getByText(IGNORE_CERT_LABEL).closest('label')
  return label.querySelector('input[type="checkbox"]')
}

function fillConnectionForm() {
  fireEvent.change(screen.getByPlaceholderText('importExport.opnsense.hostPlaceholder'),
    { target: { value: '192.0.2.10' } })
  fireEvent.change(screen.getByPlaceholderText('importExport.opnsense.apiKeyLabel'),
    { target: { value: 'k' } })
  fireEvent.change(screen.getByPlaceholderText('importExport.opnsense.apiSecretLabel'),
    { target: { value: 's' } })
}

describe('OperationsPage — OPNsense TLS verification default', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    sessionStorage.clear()
  })

  it('renders with "Ignore SSL certificate" UNCHECKED by default', () => {
    renderOperations()
    expect(getIgnoreCertCheckbox().checked).toBe(false)
    // Secure state shows no downgrade warning.
    expect(screen.queryByText('importExport.opnsense.sslWarning')).toBeNull()
  })

  it('sends verify_ssl: true on test connection by default', async () => {
    renderOperations()
    fillConnectionForm()
    fireEvent.click(screen.getByText('common.testConnection'))
    await waitFor(() => expect(opnsenseService.test).toHaveBeenCalledTimes(1))
    expect(opnsenseService.test).toHaveBeenCalledWith(
      expect.objectContaining({ verify_ssl: true })
    )
  })

  it('keeps verification ON when a saved config predates the verify_ssl key', () => {
    // A sessionStorage blob from before the key existed must not re-disable
    // verification (the old `config.verify_ssl || false` rehydration did).
    sessionStorage.setItem('opnsense_config', JSON.stringify({ host: 'h' }))
    renderOperations()
    expect(getIgnoreCertCheckbox().checked).toBe(false)
  })

  it('honors an explicitly saved opt-out and shows the downgrade warning', () => {
    sessionStorage.setItem('opnsense_config',
      JSON.stringify({ host: 'h', verify_ssl: false }))
    renderOperations()
    expect(getIgnoreCertCheckbox().checked).toBe(true)
    expect(screen.getByText('importExport.opnsense.sslWarning')).toBeTruthy()
  })

  it('sends verify_ssl: false when the user opts out via the checkbox', async () => {
    renderOperations()
    fillConnectionForm()
    fireEvent.click(getIgnoreCertCheckbox())
    fireEvent.click(screen.getByText('common.testConnection'))
    await waitFor(() => expect(opnsenseService.test).toHaveBeenCalledTimes(1))
    expect(opnsenseService.test).toHaveBeenCalledWith(
      expect.objectContaining({ verify_ssl: false })
    )
  })
})
