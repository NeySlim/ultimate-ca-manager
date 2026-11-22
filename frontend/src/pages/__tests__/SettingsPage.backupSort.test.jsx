/**
 * Settings > Backup: the archives' order lives in the address under its own scope (the sections are stacked on one
 * page): a link opens the list in it, a header click writes it, Back reads the archives again in the order it restores.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, cleanup, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter, useLocation, useNavigate } from 'react-router-dom'

vi.mock('../settings/BackupSection', () => ({
  default: ({ backupQuery, updateBackupQuery }) => (
    <>
      <output data-testid="order">{backupQuery.sort}</output>
      <button type="button" onClick={() => updateBackupQuery({ sort: 'size_asc' })}>by-size</button>
    </>
  ),
}))
vi.mock('../../hooks/usePermission', () => ({
  usePermission: () => ({
    hasPermission: () => true, canRead: () => true, canWrite: () => true, canDelete: () => true,
    isAdmin: () => true, permissions: ['*'],
  }),
}))
vi.mock('../../services/jobs.service', async (importOriginal) => {
  const real = await importOriginal()
  return { ...real, default: { get: vi.fn(), list: vi.fn(), cancel: vi.fn() } }
})

import './pageRenderingSetup.jsx'
import SettingsPage from '../SettingsPage'
import { systemService } from '../../services/system.service'
import jobsService from '../../services/jobs.service'

const at = { search: '', navigate: null }
function Where() {
  at.search = useLocation().search
  at.navigate = useNavigate()
  return null
}
const renderAt = (url) => render(<MemoryRouter initialEntries={[url]}><SettingsPage /><Where /></MemoryRouter>)
const asked = () => systemService.listBackups.mock.calls.map(([q]) => q.sort)

beforeEach(() => {
  jobsService.list.mockResolvedValue({ data: [] })
  systemService.listBackups = vi.fn().mockResolvedValue({ data: [], meta: {} })
})
afterEach(() => {
  cleanup()
  vi.clearAllMocks()
})

describe('SettingsPage: the archives\' order in the address', () => {
  it('reads the newest first by default, and writes nothing for it', async () => {
    renderAt('/settings?tab=backup')
    await waitFor(() => expect(asked()).toEqual(['created_desc']))
    expect(at.search).toBe('?tab=backup')
  })

  it('opens a link in its order, writes a new one under its scope, and follows Back', async () => {
    renderAt('/settings?tab=backup&backup-sort=name&backup-order=asc')
    expect(await screen.findByTestId('order')).toHaveTextContent('name_asc')
    await waitFor(() => expect(asked()).toEqual(['name_asc']))
    await act(async () => screen.getByText('by-size').click())
    expect(at.search).toBe('?tab=backup&backup-sort=size&backup-order=asc')
    await waitFor(() => expect(asked()).toEqual(['name_asc', 'size_asc']))
    // Another order set from outside (Back, a link): the list is read again in it, once
    await act(async () => at.navigate('/settings?tab=backup&backup-sort=created&backup-order=asc'))
    await waitFor(() => expect(asked()).toEqual(['name_asc', 'size_asc', 'created_asc']))
    expect(screen.getByTestId('order')).toHaveTextContent('created_asc')
  })
})
