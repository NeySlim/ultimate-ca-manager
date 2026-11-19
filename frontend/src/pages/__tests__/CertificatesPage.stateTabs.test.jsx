/**
 * CertificatesPage state tabs: the tab lives in the URL (`view`), a link view has the
 * tabs edit its own statuses and leaves the stored filters alone; presets save the
 * filters on screen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, waitFor, cleanup, within } from '@testing-library/react'
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
  useMobile: () => ({ isMobile: mockIsMobile, isDesktop: !mockIsMobile, isTablet: false, sidebarOpen: true, setSidebarOpen: vi.fn() }),
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
const getStats = vi.fn()
vi.mock('../../services', () => ({
  certificatesService: {
    getAll: (...args) => getAll(...args),
    getStats: (...args) => getStats(...args),
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
const tab = (id) => screen.getByRole('tab', { name: new RegExp(`^certificates\\.views\\.${id}`) })
const viewOf = (el) => el.id.split('-tab-')[1]
const selectedTabs = () => screen.getAllByRole('tab').filter((el) => el.getAttribute('aria-selected') === 'true').map(viewOf)
const where = () => screen.getByTestId('where').textContent

beforeEach(() => {
  window.localStorage.clear()
  mockIsMobile = false
  getAll.mockReset()
  getAll.mockResolvedValue({ data: [], meta: { total: 0 } })
  getStats.mockReset()
  getStats.mockResolvedValue({ data: { valid: 3, expiring: 2, expired: 0, revoked: 1, total: 1234 } })
})

describe('CertificatesPage: state tabs', () => {
  it('counts each state from the stats of the whole inventory', async () => {
    renderAt('/certificates')
    await waitFor(() => expect(tab('all')).toHaveTextContent(/^certificates\.views\.all1,234$/))
    expect(tab('expiring')).toHaveTextContent(/^certificates\.views\.expiring2$/)
    expect(tab('valid')).toHaveTextContent(/^certificates\.views\.valid3$/)
    expect(tab('expired')).toHaveTextContent(/^certificates\.views\.expired0$/)
    expect(tab('revoked')).toHaveTextContent(/^certificates\.views\.revoked1$/)
    expect(screen.getAllByRole('tab').map(viewOf)).toEqual(['all', 'expiring', 'valid', 'expired', 'revoked', 'archived'])
  })

  it('shows the orphan tab only when there are orphans, and no counter on archived', async () => {
    renderAt('/certificates')
    await waitFor(() => expect(tab('valid')).toHaveTextContent(/3$/))
    expect(screen.queryByRole('tab', { name: /views\.orphan/ })).toBeNull()
    // The stats endpoint does not count archived certificates
    expect(tab('archived')).toHaveTextContent(/^certificates\.views\.archived$/)
    cleanup()
    getStats.mockResolvedValue({ data: { valid: 3, expiring: 0, expired: 0, revoked: 1, orphan: 7, total: 4 } })
    renderAt('/certificates')
    await waitFor(() => expect(tab('orphan')).toHaveTextContent(/^certificates\.views\.orphan7$/))
  })

  it('replaces the stat tiles and the status dropdown', async () => {
    renderAt('/certificates')
    await waitFor(() => expect(tab('valid')).toHaveTextContent(/3$/))
    expect(screen.getByRole('tablist', { name: 'certificates.viewsLabel' })).toBeInTheDocument()
    expect(screen.queryByText('common.total')).toBeNull()
    expect(screen.queryByText('common.allStatus')).toBeNull()
    // The other filters keep their control, named by what they filter
    expect(screen.getByRole('button', { name: 'common.allCAs' })).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'certificates.allSources' })).toBeInTheDocument()
  })

  it('writes the tab in the URL and asks the server for that state', async () => {
    renderAt('/certificates')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    expect(selectedTabs()).toEqual(['all'])
    fireEvent.click(tab('valid'))
    await waitFor(() => expect(lastParams().status).toEqual(['valid']))
    expect(where()).toBe('?view=valid')
    expect(selectedTabs()).toEqual(['valid'])
    fireEvent.click(tab('all'))
    await waitFor(() => expect(lastParams().status).toBeUndefined())
    expect(where()).toBe('')
  })

  it('opens on the tab of the URL, with the stored filters', async () => {
    window.localStorage.setItem('ucm-filter-certs-source', JSON.stringify(['import']))
    renderAt('/certificates?view=expired')
    await waitFor(() => expect(lastParams().status).toEqual(['expired']))
    expect(lastParams().source).toEqual(['import'])
    expect(selectedTabs()).toEqual(['expired'])
  })

  it('ignores a tab the list does not know', async () => {
    renderAt('/certificates?view=bogus')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    expect(lastParams().status).toBeUndefined()
    expect(selectedTabs()).toEqual(['all'])
  })

  it('no longer reads a status stored by an earlier version', async () => {
    window.localStorage.setItem('ucm-filter-certs-status', JSON.stringify(['revoked']))
    renderAt('/certificates')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    expect(lastParams().status).toBeUndefined()
  })

  it('goes back to the first page when the tab changes', async () => {
    getAll.mockResolvedValue({ data: [{ id: 1, common_name: 'web', status: 'valid', caref: 'ca-1' }], meta: { total: 80 } })
    renderAt('/certificates')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    fireEvent.click(await screen.findByRole('button', { name: 'table.nextPage' }))
    await waitFor(() => expect(lastParams().page).toBe(2))
    fireEvent.click(tab('valid'))
    await waitFor(() => expect(lastParams()).toMatchObject({ status: ['valid'], page: 1 }))
  })
})

describe('CertificatesPage: state tabs in a link view', () => {
  it('shows the status of the link as the selected tab', async () => {
    renderAt('/certificates?status=expiring&live=true')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    expect(selectedTabs()).toEqual(['expiring'])
  })

  it('replaces the status of the link and keeps the stored filters aside', async () => {
    window.localStorage.setItem('ucm-filter-certs-ca', JSON.stringify(['1']))
    renderAt('/certificates?status=expiring&live=true')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    fireEvent.click(tab('valid'))
    await waitFor(() => expect(lastParams().status).toEqual(['valid']))
    expect(where()).toBe('?live=true&status=valid')
    expect(lastParams().ca_id).toBeUndefined()
    await settle()
    expect(JSON.parse(window.localStorage.getItem('ucm-filter-certs-ca'))).toEqual(['1'])
  })

  it('All clears the link statuses only', async () => {
    window.localStorage.setItem('ucm-filter-certs-ca', JSON.stringify(['1']))
    renderAt('/certificates?status=expiring&live=true')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    fireEvent.click(tab('all'))
    await waitFor(() => expect(where()).toBe('?live=true'))
    await settle()
    expect(lastParams().live).toBe('true')
    expect(lastParams().status).toBeUndefined()
    expect(JSON.parse(window.localStorage.getItem('ucm-filter-certs-ca'))).toEqual(['1'])
  })

  it('selects no tab for a link with several statuses and keeps them all', async () => {
    renderAt('/certificates?status=expiring&status=expired&live=true')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring', 'expired']))
    expect(selectedTabs()).toEqual([])
    // The first tab stays the one tab stop
    expect(screen.getAllByRole('tab').filter((el) => el.tabIndex === 0)).toEqual([tab('all')])
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
    window.localStorage.setItem('ucm-filter-certs-ca', JSON.stringify(['1']))
    renderAt('/certificates?status=expiring&status=expired&key_algo_prefix=RSA')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring', 'expired']))
    // The page's own chip row has a Clear filters too (it drops the whole link); this is the table's
    const overview = screen.getByTestId('overview-chips')
    const own = screen.getAllByText('table.clearFilters').filter((b) => !overview.contains(b))
    expect(own).toHaveLength(1)
    fireEvent.click(own[0])
    await settle()
    expect(JSON.parse(window.localStorage.getItem('ucm-filter-certs-ca'))).toEqual(['1'])
    expect(where()).toBe('?key_algo_prefix=RSA')
  })

  it('keeps the search when a tab rewrites the link', async () => {
    renderAt('/certificates?status=expiring&live=true')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    fireEvent.change(screen.getByPlaceholderText('certificates.searchPlaceholder'), { target: { value: 'web' } })
    await waitFor(() => expect(lastParams().search).toBe('web'))
    fireEvent.click(tab('valid'))
    await waitFor(() => expect(lastParams().status).toEqual(['valid']))
    expect(lastParams().search).toBe('web')
  })

  it('clears the search when another filter of the link changes', async () => {
    renderAt('/certificates?status=expiring&live=true')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    fireEvent.change(screen.getByPlaceholderText('certificates.searchPlaceholder'), { target: { value: 'web' } })
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
    expect(screen.queryByText('certificates.state:')).toBeNull()
  })
})

describe('CertificatesPage: filter presets and the tabs', () => {
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
    expect(where()).toBe('?status=expiring&live=true&key_algo_prefix=RSA')
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
    expect(where()).toBe(link)
  })

  it('saves the tab on screen with a preset and reopens it', async () => {
    const presets = await savePreset('/certificates?view=revoked', 'gone')
    expect(presets[0].filters.status).toEqual(['revoked'])
    cleanup()
    window.localStorage.setItem('ucm-certs-presets', JSON.stringify(presets))
    renderAt('/certificates')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    await applyPreset('gone')
    await waitFor(() => expect(lastParams().status).toEqual(['revoked']))
    expect(where()).toBe('?view=revoked')
    expect(selectedTabs()).toEqual(['revoked'])
  })

  it('a preset with several statuses applies them all: no tab, one removable chip', async () => {
    getAll.mockResolvedValue({
      data: [{ id: 1, subject: 'CN=web', common_name: 'web', status: 'expired', caref: 'ca-1' }],
      meta: { total: 1 },
    })
    window.localStorage.setItem('ucm-certs-presets', JSON.stringify([{ id: 1, name: 'old', filters: { status: ['expired', 'revoked'] } }]))
    renderAt('/certificates')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    await applyPreset('old')
    await waitFor(() => expect(lastParams().status).toEqual(['expired', 'revoked']))
    expect(selectedTabs()).toEqual([])
    // One removable chip per status
    const chips = (await screen.findAllByText('certificates.state:')).map((el) => el.parentElement)
    expect(chips.map((el) => el.textContent)).toEqual(['certificates.state:common.expired', 'certificates.state:common.revoked'])
    // Removing one leaves the other, which is then a tab again
    fireEvent.click(within(chips[0]).getByRole('button'))
    await waitFor(() => expect(lastParams().status).toHaveLength(1))
    expect(lastParams().status).toEqual(['revoked'])
    expect(selectedTabs()).toEqual(['revoked'])
    expect(where()).toBe('?view=revoked')
    expect(screen.queryByText('certificates.state:')).toBeNull()
  })

  it('a preset applied from a link view leaves the link in one step', async () => {
    window.localStorage.setItem('ucm-certs-presets', JSON.stringify([{ id: 1, name: 'old', filters: { status: ['revoked'] } }]))
    renderAt('/certificates?status=expiring&live=true')
    await waitFor(() => expect(lastParams().status).toEqual(['expiring']))
    await applyPreset('old')
    await waitFor(() => expect(lastParams().status).toEqual(['revoked']))
    expect(where()).toBe('?view=revoked')
    expect(lastParams().live).toBeUndefined()
  })

  it('drops an unknown stored value when a preset reopens its link', async () => {
    window.localStorage.setItem('ucm-certs-presets', JSON.stringify([
      { id: 1, name: 'odd', filters: { link: '?status=bogus&live=true&nonsense=1' } },
    ]))
    renderAt('/certificates')
    await waitFor(() => expect(getAll).toHaveBeenCalled())
    await applyPreset('odd')
    await waitFor(() => expect(lastParams().live).toBe('true'))
    expect(where()).toBe('?live=true')
    expect(lastParams().status).toBeUndefined()
  })
})
