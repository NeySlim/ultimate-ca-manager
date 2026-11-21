/**
 * The dialog that adds a client certificate: the way it comes as the mockup's segmented choice
 * (Generate only for who may sign), each way's form in `.form-fields` with Annuler and its action,
 * the certificates to assign as radio cards, and the result in place of the form.
 */
import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within, act } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k }) }))

import { MtlsCertificateDialog } from '../MtlsCertificateDialog'
import { validityDays } from '../validity'

function Harness({ canGenerate = true, certs = [], result = null, on = {} }) {
  const [tab, setTab] = useState('generate')
  const [gen, setGen] = useState({ name: '', validity_days: '365', ca_id: '' })
  const [imp, setImp] = useState({ name: '', pem: '' })
  const [selected, setSelected] = useState(null)
  return (
    <MtlsCertificateDialog title="Add" onClose={on.close || (() => {})} canGenerate={canGenerate} tab={tab} onTab={(w) => { setTab(w); on.tab?.(w) }}
      generateForm={gen} setGenerateForm={setGen} onGenerate={() => on.generate?.(gen)} caPicker={<div className="field full" data-testid="ca">ca</div>}
      importForm={imp} setImportForm={setImp} onImport={() => on.import?.(imp)}
      assign={{ loading: false, certs, selected, onSelect: setSelected }} onAssign={() => on.assign?.(selected)} result={result} />
  )
}

describe('MtlsCertificateDialog', () => {
  it('offers the three ways as pressed buttons and generates from the first', () => {
    const generate = vi.fn()
    render(<Harness on={{ generate }} />)
    const way = screen.getByRole('group', { name: 'account.mtlsWay' })
    expect(way).toHaveClass('segmented')
    expect(within(way).getAllByRole('button').map((b) => [b.textContent, b.getAttribute('aria-pressed')]))
      .toEqual([['account.mtlsGenerate', 'true'], ['account.mtlsImport', 'false'], ['account.mtlsAssign', 'false']])
    expect(screen.getByTestId('ca')).toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('account.mtlsValidityDays'), { target: { value: '90' } })
    const dialog = screen.getByRole('dialog')
    const actions = dialog.querySelector('form .modal-actions')
    fireEvent.click(within(actions).getByRole('button', { name: 'account.generateCertificate' }))
    expect(generate).toHaveBeenCalledWith({ name: '', validity_days: '90', ca_id: '' })
  })

  it('shows no Generate to who may not sign, and opens on Import', () => {
    render(<Harness canGenerate={false} />)
    expect(screen.queryByRole('button', { name: 'account.mtlsGenerate' })).toBeNull()
    expect(screen.getByRole('button', { name: 'account.mtlsImport' })).toHaveAttribute('aria-pressed', 'true')
    expect(screen.getByLabelText('account.mtlsPemData').tagName).toBe('TEXTAREA')
  })

  it('imports pasted PEM, its action held until there is some', async () => {
    const imported = vi.fn()
    render(<Harness on={{ import: imported }} />)
    fireEvent.click(screen.getByRole('button', { name: 'account.mtlsImport' }))
    const go = screen.getByRole('button', { name: 'account.importCertificate' })
    expect(go).toBeDisabled()
    fireEvent.change(screen.getByLabelText('account.mtlsPemData'), { target: { value: '-----BEGIN CERTIFICATE-----' } })
    await act(async () => { fireEvent.click(go) })
    expect(imported).toHaveBeenCalledWith({ name: '', pem: '-----BEGIN CERTIFICATE-----' })
  })

  it('assigns one of the offered certificates, chosen as a radio card', () => {
    const assign = vi.fn()
    const tab = vi.fn()
    render(<Harness on={{ assign, tab }} certs={[{ id: 4, name: 'web', subject: 'CN=web' }, { id: 5, name: 'vpn', subject: 'CN=vpn' }]} />)
    fireEvent.click(screen.getByRole('button', { name: 'account.mtlsAssign' }))
    expect(tab).toHaveBeenCalledWith('assign')
    const go = screen.getByRole('button', { name: 'account.assignCertificate' })
    expect(go).toBeDisabled()
    const vpn = screen.getByRole('radio', { name: /vpn/ })
    expect(vpn.closest('label')).toHaveClass('format-option')
    fireEvent.click(vpn)
    fireEvent.click(go)
    expect(assign).toHaveBeenCalledWith({ id: 5, name: 'vpn', subject: 'CN=vpn' })
  })

  it('says when no certificate can be assigned', () => {
    render(<Harness />)
    fireEvent.click(screen.getByRole('button', { name: 'account.mtlsAssign' }))
    expect(screen.getByText('account.mtlsNoAvailableCerts')).toBeInTheDocument()
  })

  it('shows the result in place of the form', () => {
    render(<Harness result={<p>issued</p>} />)
    expect(screen.getByText('issued')).toBeInTheDocument()
    expect(screen.queryByRole('group', { name: 'account.mtlsWay' })).toBeNull()
  })

  it('sends the validity typed, the default year when it is empty or unreadable', () => {
    expect(validityDays('90')).toBe(90)
    expect(validityDays('')).toBe(365)
    expect(validityDays('abc')).toBe(365)
    expect(validityDays(30)).toBe(30)
  })
})
