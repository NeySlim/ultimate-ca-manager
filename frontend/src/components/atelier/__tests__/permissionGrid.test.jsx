/**
 * The permission grid of the group dialog, read only: one row per named resource, the read, write and
 * delete columns, each offered permission marked allowed or not, never an `action:resource` scope.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'fr' } }),
}))

import { PermissionGrid } from '../PermissionGrid'

describe('PermissionGrid', () => {
  it('marks each offered permission allowed or not, under named resources and actions', () => {
    const { container } = render(<PermissionGrid label="Permissions" permissions={['delete:acme', 'read:acme', 'read:cas', 'read:*']}
      granted={(p) => p === 'read:acme'} />)
    const table = screen.getByRole('table', { name: 'Permissions' })
    expect(table).toHaveClass('compare-table', 'group-perms')
    expect(table.parentElement).toHaveClass('compare-scroll')
    expect(within(table).getAllByRole('columnheader').map((h) => h.textContent))
      .toEqual(['groups.resource', 'groups.actions.read', 'groups.actions.write', 'groups.actions.delete'])
    // a wildcard is no row of its own: it is read through `granted`
    expect(within(table).getAllByRole('rowheader').map((h) => h.textContent)).toEqual(['rbac.categories.certificateAuthorities', 'rbac.categories.acme'])
    const acme = within(table).getByRole('rowheader', { name: 'rbac.categories.acme' }).closest('tr')
    expect([...acme.querySelectorAll('td')].map((td) => td.textContent)).toEqual(['users.allowed', '', 'users.notAllowed'])
    const [read, , del] = acme.querySelectorAll('td')
    expect(read.firstElementChild).toHaveClass('flag')
    expect(read.firstElementChild).not.toHaveClass('muted')
    expect(read.querySelector('.sr-only')).toHaveTextContent('users.allowed')
    expect(del.firstElementChild).toHaveClass('flag', 'muted')
    expect(del.querySelector('.sr-only')).toHaveTextContent('users.notAllowed')
    expect(container.textContent).not.toMatch(/\w+:\w+/)
    expect(table.querySelector('input')).toBeNull()
  })

  it('lets a caller draw a leading column and the cells', () => {
    render(<PermissionGrid label="P" permissions={['read:cas']} lead={{ label: 'All', cell: ({ name }) => <b>{name}!</b> }}
      cell={({ perm, actionName, resourceName }) => <input type="checkbox" aria-label={`${actionName} ${resourceName}`} data-perm={perm} />} />)
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual(['groups.resource', 'All', 'groups.actions.read', 'groups.actions.write', 'groups.actions.delete'])
    expect(screen.getByRole('rowheader', { name: 'rbac.categories.certificateAuthorities' })).toBeTruthy()
    const cells = [...screen.getByRole('rowheader').closest('tr').querySelectorAll('td')]
    expect(cells[0]).toHaveTextContent('rbac.categories.certificateAuthorities!')
    expect(screen.getByRole('checkbox', { name: 'groups.actions.read rbac.categories.certificateAuthorities' })).toHaveAttribute('data-perm', 'read:cas')
    // the write and delete cells stay empty: nothing to grant there
    expect(cells.map((td) => td.children.length)).toEqual([1, 1, 0, 0])
  })
})
