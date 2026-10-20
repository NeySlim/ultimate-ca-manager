/**
 * SSHCAsPage: public key download and copy use the raw text returned by the service.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'
import { sshCasService } from '../../services'

import SSHCAsPage from '../SSHCAsPage'

const KEY = 'ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIabc ca@ucm'
const CAS = [{
  id: 1, descr: 'Users CA', name: 'Users CA', ca_type: 'user', key_type: 'ed25519',
  fingerprint: 'SHA256:aaa', cert_count: 0, created_at: '2026-01-01T00:00:00Z',
}]

const openDetail = async () => {
  render(<MemoryRouter><SSHCAsPage /></MemoryRouter>)
  fireEvent.click(await screen.findByText('Users CA'))
  return screen.findByText('sshCas.downloadPublicKey')
}

describe('SSHCAsPage: public key as plain text', () => {
  let blobs
  let writeText
  beforeEach(() => {
    vi.clearAllMocks()
    window.localStorage.clear()
    sshCasService.getAll = vi.fn().mockResolvedValue({ data: CAS })
    sshCasService.getPublicKey = vi.fn().mockResolvedValue(KEY)
    blobs = []
    URL.createObjectURL = vi.fn((b) => { blobs.push(b); return 'blob:x' })
    URL.revokeObjectURL = vi.fn()
    Object.defineProperty(window, 'isSecureContext', { value: true, configurable: true })
    writeText = vi.fn().mockResolvedValue()
    Object.defineProperty(navigator, 'clipboard', { value: { writeText }, configurable: true })
  })

  it('downloads a file holding exactly the key text', async () => {
    const btn = await openDetail()
    fireEvent.click(btn)
    await waitFor(() => expect(blobs.length).toBe(1))
    const text = await new Promise((res) => {
      const r = new FileReader()
      r.onload = () => res(r.result)
      r.readAsText(blobs[0])
    })
    expect(text).toBe(KEY)
  })

  it('copies the key text without JSON wrapping', async () => {
    await openDetail()
    fireEvent.click(await screen.findByText('sshCas.copyPublicKey'))
    await waitFor(() => expect(writeText).toHaveBeenCalledWith(KEY))
  })
})
