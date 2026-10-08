/**
 * Settings › HTTPS offers certificates in their last 30 days, not only those
 * with more than 30 days left (#378).
 */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

const pickerProps = vi.fn()
vi.mock('../../components/CertificatePickerModal', () => ({
  default: (props) => { pickerProps(props); return null },
}))

import './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'

describe('SettingsPage: HTTPS certificate picker', () => {
  it('asks for valid and expiring certificates with a private key', () => {
    render(
      <MemoryRouter initialEntries={['/settings?tab=https']}>
        <SettingsPage />
      </MemoryRouter>,
    )
    const { filters } = pickerProps.mock.calls.at(-1)[0]
    expect(filters.status).toEqual(['valid', 'expiring'])
    expect(filters.has_private_key).toBe(true)
  })
})
