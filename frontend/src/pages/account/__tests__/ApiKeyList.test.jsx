/**
 * The account's API keys as the settings tables: in use first, then the expired and revoked ones,
 * a search by name or prefix, pages past ten keys, the common empty block, revoke or delete per row.
 */
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render as rtlRender, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import '../../__tests__/pageRenderingSetup.jsx'
import ApiKeyList from '../ApiKeyList'

const render = (ui) => rtlRender(ui, { wrapper: MemoryRouter })
const pad = (n) => String(n).padStart(2, '0')
const rows = () => [...document.querySelectorAll('table.module-table tbody tr')]
const names = () => rows().map((tr) => tr.querySelector('th, td').textContent.trim())
const search = (value) => fireEvent.change(document.getElementById('api-key-search'), { target: { value } })

// Revoked keys come first from the API: the table puts the ones in use before them
const KEYS = Array.from({ length: 28 }, (_, i) => ({
  id: i + 1, name: `key-${pad(i + 1)}`, key_prefix: `ucm_${pad(i + 1)}ab`, is_active: i >= 6, is_expired: i === 27,
  created_at: `2026-0${(i % 9) + 1}-01T10:00:00Z`, last_used_at: null, permissions: ['read:certificates'],
}))
const list = (keys, handlers = {}) => render(<ApiKeyList keys={keys} loading={false} onRevoke={vi.fn()} onDelete={vi.fn()} onCopy={vi.fn()} {...handlers} />)

describe('API key table', () => {
  it('puts the keys in use before the expired and revoked ones, by 25 a page', () => {
    list(KEYS)
    expect(rows()).toHaveLength(25)
    expect(names().slice(0, 21)).toEqual(KEYS.slice(6, 27).map((k) => k.name))
    expect(names()[21]).toBe('key-28')
    fireEvent.click(document.querySelector('[data-page="next"]'))
    expect(names()).toEqual(['key-04', 'key-05', 'key-06'])
    expect(rows()[0]).toHaveTextContent('common.revoked')
  })

  it('finds a key by its name or its prefix', () => {
    list(KEYS)
    search('key-1')
    expect(names()).toHaveLength(10)
    search('ucm_09')
    expect(names()).toEqual(['key-09'])
    search('nothing')
    expect(screen.getByText('common.noResults')).toBeInTheDocument()
  })

  it('sorts by a header', () => {
    list(KEYS)
    fireEvent.click(document.querySelector('button[data-sort="name"]'))
    expect(names()[0]).toBe('key-01')
    fireEvent.click(document.querySelector('button[data-sort="name"]'))
    expect(names()[0]).toBe('key-28')
  })

  it('says there is no key in the common empty block', () => {
    list([])
    expect(document.getElementById('empty-api-keys')).toHaveTextContent('account.noAPIKeys')
  })

  it('revokes a key in use and deletes a revoked one', () => {
    const onRevoke = vi.fn()
    const onDelete = vi.fn()
    list([KEYS[0], KEYS[10]], { onRevoke, onDelete })
    const [active, revoked] = rows()
    expect(within(active).queryByTitle('common.delete')).toBeNull()
    fireEvent.click(within(active).getByTitle('common.revoke'))
    expect(onRevoke).toHaveBeenCalledWith(11)
    fireEvent.click(within(revoked).getByTitle('common.delete'))
    expect(onDelete).toHaveBeenCalledWith(1)
    expect(active).toHaveTextContent('ucm_11ab…')
    expect(active).not.toHaveTextContent('read:certificates')
  })
})
