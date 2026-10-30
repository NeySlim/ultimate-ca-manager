/**
 * PKCS#12 and JKS have no encoding for a post-quantum key: the dialog shows
 * them greyed out with the reason, and never sends them, for every format the
 * registry leaves out.
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { describe, expect, it, vi } from 'vitest'
import en from '../../i18n/locales/en.json'
import { GROUP_PQ, KEY_ALGORITHMS, PQ_EXPORT_EXCLUDED } from '../../lib/keyAlgorithms'

const lookup = (key) => key.split('.').reduce((node, part) => (node == null ? node : node[part]), en)
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => {
      const vars = typeof opts === 'object' && opts ? opts : {}
      const template = lookup(key) ?? (typeof opts === 'string' ? opts : vars.defaultValue ?? key)
      return String(template).replace(/\{\{(\w+)\}\}/g, (_m, name) => (vars[name] ?? `{{${name}}}`))
    },
  }),
  initReactI18next: { type: '3rdParty', init: () => {} },
  Trans: ({ children }) => children,
}))

import { ExportModal } from '../ExportModal'

const FORMAT_LABELS = { pem: 'PEM', der: 'DER', pkcs7: 'P7B / PKCS#7', pkcs12: 'P12 / PKCS#12', jks: 'JKS', key: en.export.formats.privateKey }
const formatButton = (key) => screen.getByText(FORMAT_LABELS[key]).closest('button')
// Every format tile the dialog renders, whatever its list holds
const renderedFormatButtons = () => [...screen.getByText(en.export.format).parentElement.querySelectorAll('button')]

const renderModal = (props = {}) => {
  const onExport = vi.fn().mockResolvedValue(undefined)
  render(<ExportModal open onClose={() => {}} entityName="pq.example.com" hasPrivateKey canExportKey
    onExport={onExport} {...props} />)
  return onExport
}

const PQ_NAMES = [...KEY_ALGORITHMS.filter(a => a.group === GROUP_PQ).map(a => a.label), 'SLH-DSA-SHA2-128s']

describe('ExportModal with a post-quantum key', () => {
  it.each(PQ_NAMES)('greys out what the registry excludes for %s, with the reason', (name) => {
    renderModal({ keyAlgorithm: name })
    expect(PQ_EXPORT_EXCLUDED).toEqual(expect.arrayContaining(['pkcs12', 'jks']))
    const excluded = PQ_EXPORT_EXCLUDED.map(formatButton)
    for (const button of excluded) {
      expect(button).toBeDisabled()
      expect(button).toHaveAttribute('title', expect.stringContaining(name))
    }
    const others = renderedFormatButtons().filter(b => !excluded.includes(b))
    expect(others.length).toBeGreaterThan(0)
    for (const button of others) expect(button).toBeEnabled()
  })

  it('never sends PKCS#12 for an ML-DSA key, even as the default format', async () => {
    const onExport = renderModal({ keyAlgorithm: 'ML-DSA-65', defaultFormat: 'pkcs12' })
    fireEvent.click(formatButton('pkcs12'))
    fireEvent.submit(formatButton('pem').closest('form'))
    await waitFor(() => expect(onExport).toHaveBeenCalledTimes(1))
    expect(onExport.mock.calls[0][0]).toBe('pem')
  })

  it('keeps every key format for a classical key', () => {
    renderModal({ keyAlgorithm: 'RSA' })
    const buttons = renderedFormatButtons()
    expect(buttons.length).toBeGreaterThanOrEqual(Object.keys(FORMAT_LABELS).length)
    for (const button of buttons) expect(button).toBeEnabled()
  })
})
