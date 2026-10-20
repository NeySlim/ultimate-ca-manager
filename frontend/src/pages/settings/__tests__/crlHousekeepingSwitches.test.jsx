/**
 * The two CRL housekeeping switches of the HSTS card: state from settings,
 * off when absent, updateSetting on change, locked without admin:settings.
 */
import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, loading: _loading, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label, value, disabled }) => (
    <div data-field="">{label}<input readOnly value={value ?? ''} disabled={disabled} /></div>
  ),
  Textarea: ({ label, value, disabled }) => (
    <div data-field="">{label}<textarea readOnly value={value ?? ''} disabled={disabled} /></div>
  ),
  Select: ({ label }) => <div data-field="">{label}</div>,
  Badge: ({ children }) => <span>{children}</span>,
  LoadingSpinner: () => <span>loading</span>,
  ExperimentalBadge: () => <span>experimental</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
  DetailGrid: ({ children }) => <div>{children}</div>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))

vi.mock('../../../components/ui/ToggleSwitch', () => ({
  ToggleSwitch: ({ label, description, checked, disabled, onChange }) => (
    <button type="button" role="switch" aria-label={label} aria-description={description}
      aria-checked={checked} disabled={disabled} onClick={() => onChange(!checked)} />
  ),
}))

import SecuritySection from '../SecuritySection'

const OPERATOR = ['read:settings', 'write:settings']
const ADMIN = [...OPERATOR, 'admin:settings']
const DELETE = 'settings.crlAutoDeleteExpiredRevoked'
const PURGE = 'settings.crlAutoPurgeStaleSerials'

function renderSecurity(perms, settings = {}, updateSetting = vi.fn()) {
  render(
    <SecuritySection
      settings={{ hsts_env_locked: [], ...settings }}
      updateSetting={updateSetting} handleSave={vi.fn()} saving={false}
      hasPermission={(p) => perms.includes(p)} encryptionStatus={null}
      anomalies={[]} anomaliesLoading={false} loadAnomalies={vi.fn()}
      mtlsSettings={{}} setMtlsSettings={vi.fn()} mtlsLoading={false} mtlsSaving={false}
      handleMtlsSave={vi.fn()} cas={[]}
    />
  )
  return updateSetting
}

const toggle = (key) => screen.getByRole('switch', { name: key })

describe('CRL housekeeping switches', () => {
  it('are off when the settings do not carry the keys', () => {
    renderSecurity(ADMIN)
    expect(toggle(DELETE).getAttribute('aria-checked')).toBe('false')
    expect(toggle(PURGE).getAttribute('aria-checked')).toBe('false')
  })

  it('follow each key independently', () => {
    renderSecurity(ADMIN, { crl_auto_delete_expired_revoked: true, crl_auto_purge_stale_serials: false })
    expect(toggle(DELETE).getAttribute('aria-checked')).toBe('true')
    expect(toggle(PURGE).getAttribute('aria-checked')).toBe('false')
  })

  it('carry their description keys', () => {
    renderSecurity(ADMIN)
    expect(toggle(DELETE).getAttribute('aria-description')).toBe('settings.crlAutoDeleteExpiredRevokedDesc')
    expect(toggle(PURGE).getAttribute('aria-description')).toBe('settings.crlAutoPurgeStaleSerialsDesc')
  })

  it('send the new boolean under the setting key for an administrator', () => {
    const updateSetting = renderSecurity(ADMIN, { crl_auto_purge_stale_serials: true })
    fireEvent.click(toggle(DELETE))
    expect(updateSetting).toHaveBeenCalledWith('crl_auto_delete_expired_revoked', true)
    fireEvent.click(toggle(PURGE))
    expect(updateSetting).toHaveBeenCalledWith('crl_auto_purge_stale_serials', false)
  })

  it('are read-only for an operator, values shown, save button kept', () => {
    const updateSetting = renderSecurity(OPERATOR, { crl_auto_delete_expired_revoked: true })
    expect(toggle(DELETE).disabled).toBe(true)
    expect(toggle(PURGE).disabled).toBe(true)
    expect(toggle(DELETE).getAttribute('aria-checked')).toBe('true')
    fireEvent.click(toggle(DELETE))
    expect(updateSetting).not.toHaveBeenCalled()
    expect(screen.getAllByText('common.saveChanges').length).toBeGreaterThan(0)
  })

  it('sit after the OCSP responder settings and before the card save button', () => {
    renderSecurity(ADMIN)
    const card = toggle(DELETE).closest('section')
    const ocsp = screen.getByRole('switch', { name: 'settings.ocspResponderAutoRenew' })
    const save = [...card.querySelectorAll('button')].find((b) => b.textContent === 'common.saveChanges')
    const order = [ocsp, toggle(DELETE), toggle(PURGE), save]
    for (let i = 1; i < order.length; i++) {
      expect(order[i - 1].compareDocumentPosition(order[i]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy()
    }
  })
})
