import { beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ downloadBlob: vi.fn() }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn() }),
}))

vi.mock('../../../hooks', () => ({
  useClipboard: () => ({ copy: vi.fn() }),
}))

vi.mock('../../../lib/utils', async () => ({
  ...(await vi.importActual('../../../lib/utils')),
  downloadBlob: mocks.downloadBlob,
}))

vi.mock('../../../components', async () => {
  const detailCard = await vi.importActual('../../../components/DetailCard.jsx')
  return {
    Badge: ({ children }) => <span>{children}</span>,
    Button: ({ children, ...props }) => <button {...props}>{children}</button>,
    CompactSection: detailCard.CompactSection,
    CompactGrid: detailCard.CompactGrid,
    CompactField: detailCard.CompactField,
    CompactStats: detailCard.CompactStats,
    CompactHeader: detailCard.CompactHeader,
  }
})

import OrderDetailPanel, { http01Url } from '../OrderDetailPanel'

const order = (challenge_type, challenges) => ({
  id: 1,
  domains: Object.keys(challenges),
  environment: 'production',
  status: 'pending',
  challenge_type,
  challenges,
})

const http01 = {
  token: 'tok-123',
  key_authorization: 'tok-123.thumbprint',
  identifier_type: 'dns',
}

const noop = () => {}
const renderPanel = (o) => render(
  <OrderDetailPanel order={o} onDownloadCert={noop} onViewCertificate={noop}
    onRenewCertificate={noop} onVerifyChallenge={noop} onFinalizeOrder={noop} onDeleteOrder={noop} />
)

describe('OrderDetailPanel HTTP-01 challenge', () => {
  beforeEach(() => mocks.downloadBlob.mockClear())

  it('shows the URL and the key authorization the CA will fetch', () => {
    renderPanel(order('http-01', { 'www.example.com': http01 }))
    expect(screen.getByText('http://www.example.com/.well-known/acme-challenge/tok-123')).toBeInTheDocument()
    expect(screen.getByText('tok-123.thumbprint')).toBeInTheDocument()
    expect(screen.getByText('acme.http01Hint')).toBeInTheDocument()
  })

  it('downloads a file named after the token holding the key authorization', async () => {
    renderPanel(order('http-01', { 'www.example.com': http01 }))
    fireEvent.click(screen.getByText('acme.http01DownloadFile'))
    expect(mocks.downloadBlob).toHaveBeenCalledTimes(1)
    const [blob, filename] = mocks.downloadBlob.mock.calls[0]
    expect(filename).toBe('tok-123')
    // text/plain makes browsers append .txt, and the CA fetches the bare token
    expect(blob.type).toBe('application/octet-stream')
    const text = await new Promise((resolve) => {
      const reader = new FileReader()
      reader.onload = () => resolve(reader.result)
      reader.readAsText(blob)
    })
    expect(text).toBe('tok-123.thumbprint')
  })

  it('shows nothing HTTP-01 specific for a DNS-01 order', () => {
    renderPanel(order('dns-01', { 'www.example.com': { ...http01, dns_txt_name: '_acme-challenge.www.example.com', dns_txt_value: 'v' } }))
    expect(screen.queryByText('acme.http01DownloadFile')).not.toBeInTheDocument()
    expect(screen.queryByText('acme.http01Hint')).not.toBeInTheDocument()
  })

  it('brackets an IPv6 identifier in the URL', () => {
    expect(http01Url('2001:db8::1', { ...http01, identifier_type: 'ip' }))
      .toBe('http://[2001:db8::1]/.well-known/acme-challenge/tok-123')
    expect(http01Url('192.0.2.10', { ...http01, identifier_type: 'ip' }))
      .toBe('http://192.0.2.10/.well-known/acme-challenge/tok-123')
  })

  it('brackets an IPv6 identifier on an order stored without identifier_type', () => {
    const { identifier_type: _omit, ...legacy } = http01
    expect(http01Url('2001:db8::1', legacy))
      .toBe('http://[2001:db8::1]/.well-known/acme-challenge/tok-123')
  })
})
