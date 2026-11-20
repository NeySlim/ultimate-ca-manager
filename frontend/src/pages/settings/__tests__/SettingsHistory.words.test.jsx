/** History of the saves in the reader's language: the audit log's English names and fixed details translated. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (key) => `tr(${key})` }) }))

import SettingsHistory from '../SettingsHistory'

const entry = (id, fields) => ({ id, username: 'admin', timestamp: '2026-10-08T14:29:00Z', ...fields })

describe('SettingsHistory words', () => {
  it('translates the names and details the audit log writes in English', () => {
    render(<SettingsHistory entries={[
      entry(1, { action: 'settings_update', resource_name: 'Email/SMTP Settings', details: 'Updated email/SMTP settings' }),
      entry(2, { action: 'ct_settings_updated', details: 'Certificate Transparency settings updated' }),
    ]} />)
    expect(screen.getByText('tr(settings.history.smtp)')).toBeInTheDocument()
    expect(screen.getByText('tr(settings.history.smtpDetail)')).toBeInTheDocument()
    expect(screen.getByText('tr(settings.history.ct)')).toBeInTheDocument()
    expect(screen.getByText('tr(settings.history.ctDetail)')).toBeInTheDocument()
    expect(screen.queryByText(/Email\/SMTP/)).toBeNull()
  })

  it('keeps a detail it does not know as recorded', () => {
    render(<SettingsHistory entries={[entry(3, { action: 'mtls_settings_update', resource_name: 'mTLS', details: 'Updated mTLS settings: enabled' })]} />)
    expect(screen.getByText('tr(settings.history.mtls)')).toBeInTheDocument()
    expect(screen.getByText('Updated mTLS settings: enabled')).toBeInTheDocument()
  })
})
