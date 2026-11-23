/**
 * The profile of a user in the dock reads as typed rows: an absent e-mail or sign-in is muted,
 * the second factor is a state, the role's explanation is a help folded behind its button.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'en' } }),
}))
vi.mock('../../../services', () => ({ rolesService: {}, groupsService: {} }))

import { UserProfile } from '../UserPanels'

const base = { id: 7, username: 'jdoe', role: 'operator', active: true, created_at: '2026-01-09T10:00:00Z' }
const rowOf = (term) => screen.getByText(term, { selector: 'dt' }).closest('div.row')

describe('UserProfile facts', () => {
  it('draws Identity and Access as dl.kv, never the flat dl.props', () => {
    const { container } = render(<UserProfile user={base} sso={{}} />)
    expect(container.querySelectorAll('dl.kv')).toHaveLength(2)
    expect(container.querySelector('dl.props')).toBeNull()
  })

  it('mutes a missing e-mail and a sign-in that never happened, out of the value class', () => {
    render(<UserProfile user={{ ...base, email: '', last_login: null }} sso={{}} />)
    const email = rowOf('users.email').querySelector('dd')
    expect(email).toHaveClass('absent')
    expect(email).toHaveTextContent('—')
    const seen = rowOf('users.lastSeen').querySelector('dd')
    expect(seen).toHaveClass('absent')
    expect(seen).toHaveTextContent('common.never')
  })

  it('sets a long address on its own line, a short one beside its term', () => {
    const { unmount } = render(<UserProfile user={{ ...base, email: 'operator_mwsgx7ox_x7agm@example.test' }} sso={{}} />)
    expect(rowOf('users.email')).toHaveClass('long')
    expect(rowOf('users.login')).not.toHaveClass('long')
    unmount()
    render(<UserProfile user={{ ...base, email: 'j@example.org' }} sso={{}} />)
    expect(rowOf('users.email')).not.toHaveClass('long')
  })

  it('writes the second factor as a state, neutral when off', () => {
    render(<UserProfile user={{ ...base, two_factor_enabled: false }} sso={{}} />)
    const off = rowOf('users.twoFactor').querySelector('dd.v .badge')
    expect(off).toHaveClass('muted')
    expect(off).toHaveTextContent('common.disabled')
  })

  it('folds the role explanation behind its help button, out of the value', () => {
    render(<UserProfile user={base} sso={{}} />)
    const row = rowOf('common.role')
    expect(row.querySelector('dd.v')).toHaveTextContent(/^common\.operator$/)
    const help = row.querySelector('dd.help')
    expect(help).toHaveTextContent('users.roleDesc.operator')
    expect(help).not.toBeVisible()
    const button = row.querySelector('dt button.tip')
    expect(button).toHaveAttribute('aria-controls', help.id)
    fireEvent.click(button)
    expect(help).toBeVisible()
  })

  it('names a custom role under the base role, as a second line of the value', () => {
    render(<UserProfile user={{ ...base, custom_role_name: 'PKI ops' }} sso={{}} />)
    const row = rowOf('common.role')
    expect(row.querySelector('dd.v .sub')).toHaveTextContent('users.customRoleOf {"name":"PKI ops"}')
    expect(row.querySelector('dd.help')).toBeNull()
  })
})
