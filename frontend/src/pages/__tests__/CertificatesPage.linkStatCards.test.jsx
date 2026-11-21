/**
 * CertificatesPage in a link view: a status card edits the link's filters in the
 * URL and leaves the stored ones alone; presets save the filters on screen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react'
import { MemoryRouter, useLocation } from 'react-router-dom'

// Stable across renders: t and showError are loader dependencies, a fresh one reloads in a loop
const stable = vi.hoisted(() => ({
  i18n: {
    t: (key, opts) => (opts && typeof opts.count === 'number' ? `${key}:${opts.count}` : key),
    i18n: { language: 'en', changeLanguage: () => {}, on: () => {}, off: () => {} },
  },
  notify: {
    showSuccess: () => {}, showError: () => {}, showInfo: () => {}, showWarning: () => {},
    showConfirm: () => Promise.resolve(false), showPrompt: () => Promise.resolve(null),
  },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => stable.i18n,
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

let mockIsMobile = false

vi.mock('../../contexts', () => ({
  useNotification: () => stable.notify,
  useMobile: () => ({ isMobile: mockIsMobile, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
  useInspector: () => ({
    openEntity: vi.fn(), closeEntity: vi.fn(), closeAll: vi.fn(), windows: [], prefs: { sameWindow: true, closeOnNav: true }, updatePrefs: () => {},
  }),
}))

vi.mock('../../hooks', async () => {
  const actual = await vi.importActual('../../hooks/usePersistedState')
  return {
    usePersistedState: actual.usePersistedState,
    usePermission: () => ({
      canWrite: () => true, canDelete: () => true, hasPermission: () => true, canRead: () => true,
    }),
    useRecentHistory: () => ({ addToHistory: vi.fn(), history: [] }),
    useFavorites: () => ({ favorites: [], toggleFavorite: vi.fn(), isFavorite: () => false }),
    useWebSocket: () => ({ muteToasts: vi.fn(), subscribe: vi.fn(() => vi.fn()), isConnected: false }),
  }
})

const getAll = vi.fn()
vi.mock('../../services', () => ({
  certificatesService: {
    getAll: (...args) => getAll(...args),
    getStats: vi.fn().mockResolvedValue({ data: { valid: 3, expiring: 0, expired: 0, revoked: 1, total: 4 } }),
    revoke: vi.fn().mockResolvedValue({ data: {} }),
  },
  casService: { getAll: vi.fn().mockResolvedValue({ data: [{ id: 1, refid: 'ca-1', descr: 'CA 1' }] }) },
  truststoreService: { addFromCA: vi.fn().mockResolvedValue({ data: {} }) },
}))

import CertificatesPage from '../CertificatesPage'


const Where = () => <output data-testid="where">{useLocation().search}</output>
const renderAt = (url) => render(<MemoryRouter initialEntries={[url]}><CertificatesPage /><Where /></MemoryRouter>)
const lastParams = () => getAll.mock.calls[getAll.mock.calls.length - 1][0]
const settle = () => new Promise((r) => setTimeout(r, 400)) // past the debounce of usePersistedState
const card = (label) => screen.getAllByText(label)[0]

describe('CertificatesPage: status cards in a link view', () => {
  beforeEach(() => {
    window.localStorage.clear()
    getAll.mockReset()
    getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
  })

  it('adds the status to the link and keeps the stored filter', async () => {
    window.localStorage.setItem('ucm-filter-certs-status', JSON.stringify(['revoked']))
    renderAt('/certificates?status=expiring&live=true')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    fireEvent.click(card('common.valid'))
    await waitFor(() => expect(lastParams().status).toEqual(['expiring', 'valid']))
    expect(screen.getByTestId('where').textContent).toBe('?live=true&status=expiring&status=valid')
    await settle()
    expect(JSON.parse(window.localStorage.getItem('ucm-filter-certs-status'))).toEqual(['revoked'])
  })

  it('removes a status of the link when its card is clicked again', async () => {
    renderAt('/certificates?status=expiring&live=true')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    fireEvent.click(card('common.expiring'))
    await waitFor(() => expect(lastParams().status).toBeUndefined())
    expect(screen.getByTestId('where').textContent).toBe('?live=true')
  })

  it('Total clears the link statuses only', async () => {
    window.localStorage.setItem('ucm-filter-certs-status', JSON.stringify(['revoked']))
    renderAt('/certificates?status=expiring&live=true')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    fireEvent.click(card('common.total'))
    await waitFor(() => expect(screen.getByTestId('where').textContent).toBe('?live=true'))
    await settle()
    expect(lastParams().live).toBe('true')
    expect(JSON.parse(window.localStorage.getItem('ucm-filter-certs-status'))).toEqual(['revoked'])
  })

  it('saves a preset with the filters of the link, not empty ones', async () => {
    renderAt('/certificates?status=expiring')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    fireEvent.click(screen.getByTitle('table.filterPresets'))
    fireEvent.click(await screen.findByText('table.saveFilters'))
    fireEvent.change(screen.getByPlaceholderText('table.presetName'), { target: { value: 'soon' } })
    fireEvent.click(screen.getByText('common.save'))
    const presets = JSON.parse(window.localStorage.getItem('ucm-certs-presets'))
    expect(presets[0].filters.status).toEqual(['expiring'])
  })

  it('Clear filters of the table in a link view leaves the stored filters alone', async () => {
    window.localStorage.setItem('ucm-filter-certs-status', JSON.stringify(['revoked']))
    window.localStorage.setItem('ucm-filter-certs-ca', JSON.stringify(['1']))
    renderAt('/certificates?status=expiring&key_algo_prefix=RSA')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    // The page's own chip row has a Clear filters too (it drops the whole link); this is the table's
    const overview = screen.getByTestId('overview-chips')
    const own = screen.getAllByText('table.clearFilters').filter((b) => !overview.contains(b))
    expect(own).toHaveLength(1)
    fireEvent.click(own[0])
    await settle()
    expect(JSON.parse(window.localStorage.getItem('ucm-filter-certs-status'))).toEqual(['revoked'])
    expect(JSON.parse(window.localStorage.getItem('ucm-filter-certs-ca'))).toEqual(['1'])
    expect(screen.getByTestId('where').textContent).toContain('key_algo_prefix=RSA')
  })

  it('keeps the search when a status card rewrites the link', async () => {
    renderAt('/certificates?status=expiring&live=true')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    fireEvent.change(screen.getByPlaceholderText(/common.search/), { target: { value: 'web' } })
    await waitFor(() => expect(lastParams().search).toBe('web'))
    fireEvent.click(card('common.valid'))
    await waitFor(() => expect(lastParams().status).toEqual(['expiring', 'valid']))
    expect(lastParams().search).toBe('web')
  })

  it('clears the search when another filter of the link changes', async () => {
    renderAt('/certificates?status=expiring&live=true')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    fireEvent.change(screen.getByPlaceholderText(/common.search/), { target: { value: 'web' } })
    await waitFor(() => expect(lastParams().search).toBe('web'))
    const chip = screen.getByText('overview.filter.live:').parentElement
    fireEvent.click(chip.querySelector('button'))
    await waitFor(() => expect(lastParams().search).toBeUndefined())
  })

  it('shows the status of the link once, in the overview chips', async () => {
    // With rows, so the table draws its own chip row instead of the empty state
    getAll.mockResolvedValue({
      data: [{ id: 1, subject: 'CN=web', common_name: 'web', status: 'expiring', caref: 'ca-1' }],
      meta: { total: 1 },
    })
    renderAt('/certificates?status=expiring&live=true')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    expect(screen.getByText('overview.filter.status:')).toBeTruthy()
    expect(screen.queryByText('common.status:')).toBeNull()
  })

  const savePreset = async (url, name) => {
    renderAt(url)
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(screen.getByTitle('table.filterPresets'))
    fireEvent.click(await screen.findByText('table.saveFilters'))
    fireEvent.change(screen.getByPlaceholderText('table.presetName'), { target: { value: name } })
    fireEvent.click(screen.getByText('common.save'))
    return JSON.parse(window.localStorage.getItem('ucm-certs-presets'))
  }
  const applyPreset = async (name) => {
    fireEvent.click(screen.getByTitle('table.filterPresets'))
    fireEvent.click(await screen.findByText(name))
  }

  it('a preset saved in a link view reopens the same view', async () => {
    const presets = await savePreset('/certificates?status=expiring&live=true&key_algo_prefix=RSA', 'rsa')
    expect(presets[0].filters.status).toEqual(['expiring'])
    cleanup()
    window.localStorage.setItem('ucm-certs-presets', JSON.stringify(presets))
    renderAt('/certificates')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    await applyPreset('rsa')
    await waitFor(() => expect(lastParams()).toMatchObject({ status: ['expiring'], live: 'true', key_algo_prefix: 'RSA' }))
    expect(screen.getByTestId('where').textContent).toBe('?status=expiring&live=true&key_algo_prefix=RSA')
  })

  it('saves and reopens a link without status, as the compliance counters emit', async () => {
    const link = '?live=true&key_algo_prefix=RSA&key_bits_below=3072'
    const presets = await savePreset(`/certificates${link}`, 'weak-rsa')
    cleanup()
    window.localStorage.setItem('ucm-certs-presets', JSON.stringify(presets))
    renderAt('/certificates')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    await applyPreset('weak-rsa')
    await waitFor(() => expect(lastParams()).toMatchObject({ live: 'true', key_algo_prefix: 'RSA', key_bits_below: '3072' }))
    expect(screen.getByTestId('where').textContent).toBe(link)
  })

  it('a preset saved before links existed still applies its saved filters', async () => {
    window.localStorage.setItem('ucm-certs-presets', JSON.stringify([{ id: 1, name: 'old', filters: { status: ['revoked'] } }]))
    renderAt('/certificates')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    await applyPreset('old')
    await waitFor(() => expect(lastParams().status).toEqual(['revoked']))
    expect(screen.getByTestId('where').textContent).toBe('')
  })

  it('drops an unknown stored value when a preset reopens its link', async () => {
    window.localStorage.setItem('ucm-certs-presets', JSON.stringify([
      { id: 1, name: 'odd', filters: { link: '?status=bogus&live=true&nonsense=1' } },
    ]))
    renderAt('/certificates')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    await applyPreset('odd')
    await waitFor(() => expect(lastParams().live).toBe('true'))
    expect(screen.getByTestId('where').textContent).toBe('?live=true')
    expect(lastParams().status).toBeUndefined()
  })
})
