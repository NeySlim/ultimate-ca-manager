/**
 * An option the chosen format cannot carry is neither shown nor sent: DER
 * holds one certificate, P7B certificates only (the server answers 400).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'

import { ExportModal } from '../ExportModal'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : (fallback?.defaultValue || key)),
  }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))

const open = (format) => {
  const onExport = vi.fn().mockResolvedValue(undefined)
  render(
    <ExportModal open onClose={() => {}} entityType="certificate" entityName="web"
      hasPrivateKey canExportKey onExport={onExport} />
  )
  fireEvent.click(screen.getByText(format))
  return onExport
}

const submit = async (onExport) => {
  fireEvent.submit(document.querySelector('form'))
  await waitFor(() => expect(onExport).toHaveBeenCalledTimes(1))
  return onExport.mock.calls[0][1]
}

describe('ExportModal options per format', () => {
  it('DER offers neither the chain nor the key and sends neither', async () => {
    const onExport = open('DER')
    expect(screen.queryByText('Include CA chain')).toBeNull()
    expect(screen.queryByText('Include private key')).toBeNull()
    const opts = await submit(onExport)
    expect(opts.includeChain).toBe(false)
    expect(opts.includeKey).toBe(false)
  })

  it('P7B offers the chain but not the key', async () => {
    const onExport = open('P7B / PKCS#7')
    expect(screen.getByText('Include CA chain')).toBeInTheDocument()
    expect(screen.queryByText('Include private key')).toBeNull()
    const opts = await submit(onExport)
    expect(opts.includeKey).toBe(false)
    expect(opts.includeChain).toBe(true)
  })

  it('PEM still offers both', () => {
    open('PEM')
    expect(screen.getByText('Include CA chain')).toBeInTheDocument()
    expect(screen.getByText('Include private key')).toBeInTheDocument()
  })
})
