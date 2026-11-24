/**
 * A long DNS value (an Active Directory realm, a protocol URL) wraps after its dots and slashes, as the
 * HTTPS host name does (Breakable), instead of being cut anywhere; the text and its copy stay whole.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../contexts', () => ({
  useNotification: () => ({ showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(), showInfo: vi.fn() }),
}))

vi.mock('../../../services', () => ({
  adConnectorsService: { test: vi.fn() },
}))

import AdConnectorForm from '../AdConnectorForm'
import CopyableUrl from '../CopyableUrl'

const REALM = 'RESEARCH.EMEA.CORPORATE-HOLDING.EXAMPLE.COM'

describe('a long DNS value', () => {
  it('the realm of a saved AD connector breaks after its dots and hyphen only', () => {
    render(<AdConnectorForm config={{ id: 1, realm: REALM, servers: ['dc1.corp.local'], port: 389, enabled: false }}
      onSave={vi.fn()} onCancel={vi.fn()} />)
    const value = screen.getByText((_, el) => el?.tagName === 'SPAN' && el.classList.contains('mono') && el.textContent === REALM)
    expect(value.innerHTML).toBe('RESEARCH.<wbr>EMEA.<wbr>CORPORATE-<wbr>HOLDING.<wbr>EXAMPLE.<wbr>COM')
  })

  it('a protocol URL breaks after its separators, its text whole', () => {
    const url = 'https://pki-frontend.research.example.com/scep/pkiclient.exe'
    const { container } = render(<CopyableUrl label="SCEP URL" value={url} />)
    const value = container.querySelector('.mono')
    expect(value).toHaveTextContent(url)
    expect(value.innerHTML).toBe('https:<wbr>/<wbr>/<wbr>pki-<wbr>frontend.<wbr>research.<wbr>example.<wbr>com/<wbr>scep/<wbr>pkiclient.<wbr>exe')
  })
})
