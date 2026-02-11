/**
 * Hooks & Contexts Tests
 * Tests for custom hooks and context providers (AuthContext has its own tests)
 */
import { describe, it, expect, vi, beforeEach, beforeAll } from 'vitest'
import { render, screen, act, renderHook } from '@testing-library/react'

// Fix ResizeObserver to be constructable (setup.js mock isn't a proper class)
beforeAll(() => {
  global.ResizeObserver = class ResizeObserver {
    constructor(cb) { this._cb = cb }
    observe() {}
    unobserve() {}
    disconnect() {}
  }
})

// ════════════════════════════════════════════════════════════════════
// NotificationContext Tests
// ════════════════════════════════════════════════════════════════════

// Must mock Radix UI Toast/Dialog before import
vi.mock('@radix-ui/react-toast', () => ({
  Provider: ({ children }) => <div>{children}</div>,
  Root: ({ children }) => <div>{children}</div>,
  Title: ({ children }) => <div>{children}</div>,
  Description: ({ children }) => <div>{children}</div>,
  Action: ({ children }) => <div>{children}</div>,
  Close: ({ children }) => <div>{children}</div>,
  Viewport: () => null,
}))

vi.mock('@radix-ui/react-dialog', () => ({
  Root: ({ children, open }) => open ? <div>{children}</div> : null,
  Trigger: ({ children }) => <div>{children}</div>,
  Portal: ({ children }) => <div>{children}</div>,
  Overlay: ({ children }) => <div>{children}</div>,
  Content: ({ children }) => <div>{children}</div>,
  Title: ({ children }) => <div>{children}</div>,
  Description: ({ children }) => <div>{children}</div>,
  Close: ({ children }) => <div>{children}</div>,
}))

import { NotificationProvider, useNotification } from '../../contexts/NotificationContext'

function NotifTestComponent() {
  const ctx = useNotification()
  return (
    <div>
      <button onClick={() => ctx.showSuccess('OK!')}>success</button>
      <button onClick={() => ctx.showError('Fail!')}>error</button>
      <button onClick={() => ctx.showWarning('Warn!')}>warning</button>
      <button onClick={() => ctx.showInfo('Info!')}>info</button>
      <span data-testid="has-confirm">{typeof ctx.showConfirm}</span>
      <span data-testid="has-prompt">{typeof ctx.showPrompt}</span>
    </div>
  )
}

describe('NotificationContext', () => {
  it('provides notification methods to children', () => {
    render(
      <NotificationProvider>
        <NotifTestComponent />
      </NotificationProvider>
    )
    expect(screen.getByText('success')).toBeInTheDocument()
    expect(screen.getByTestId('has-confirm').textContent).toBe('function')
    expect(screen.getByTestId('has-prompt').textContent).toBe('function')
  })

  it('showSuccess creates a toast', () => {
    render(
      <NotificationProvider>
        <NotifTestComponent />
      </NotificationProvider>
    )
    act(() => {
      screen.getByText('success').click()
    })
  })

  it('showError creates a toast', () => {
    render(
      <NotificationProvider>
        <NotifTestComponent />
      </NotificationProvider>
    )
    act(() => {
      screen.getByText('error').click()
    })
  })

  it('useNotification throws outside provider', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<NotifTestComponent />)).toThrow()
    spy.mockRestore()
  })
})


// ════════════════════════════════════════════════════════════════════
// MobileContext Tests
// ════════════════════════════════════════════════════════════════════
import { MobileProvider, useMobile } from '../../contexts/MobileContext'

function MobileTestComponent() {
  const ctx = useMobile()
  return (
    <div>
      <span data-testid="isMobile">{String(ctx.isMobile)}</span>
      <span data-testid="isTablet">{String(ctx.isTablet)}</span>
      <span data-testid="explorerOpen">{String(ctx.explorerOpen)}</span>
      <button onClick={ctx.toggleExplorer}>toggle</button>
    </div>
  )
}

describe('MobileContext', () => {
  beforeEach(() => {
    window.matchMedia = vi.fn().mockImplementation(query => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }))
  })

  it('provides mobile state to children', () => {
    render(
      <MobileProvider>
        <MobileTestComponent />
      </MobileProvider>
    )
    expect(screen.getByTestId('isMobile')).toBeInTheDocument()
    expect(screen.getByTestId('isTablet')).toBeInTheDocument()
  })

  it('defaults to desktop on wide screens', () => {
    render(
      <MobileProvider>
        <MobileTestComponent />
      </MobileProvider>
    )
    expect(screen.getByTestId('isMobile').textContent).toBe('false')
  })

  it('sidebar can be toggled', () => {
    render(
      <MobileProvider>
        <MobileTestComponent />
      </MobileProvider>
    )
    const initial = screen.getByTestId('explorerOpen').textContent
    act(() => {
      screen.getByText('toggle').click()
    })
    const after = screen.getByTestId('explorerOpen').textContent
    expect(after).not.toBe(initial)
  })
})


// ════════════════════════════════════════════════════════════════════
// useFormData Hook Tests
// ════════════════════════════════════════════════════════════════════
import { useFormData, useModals } from '../../hooks/useCommon'

describe('useFormData', () => {
  it('initializes with given data', () => {
    const { result } = renderHook(() => useFormData({ name: 'test', count: 0 }))
    expect(result.current.formData).toEqual({ name: 'test', count: 0 })
  })

  it('updateField updates a single field', () => {
    const { result } = renderHook(() => useFormData({ name: '', email: '' }))
    act(() => {
      result.current.updateField('name', 'John')
    })
    expect(result.current.formData.name).toBe('John')
    expect(result.current.formData.email).toBe('')
  })

  it('updateNested updates nested object field', () => {
    const { result } = renderHook(() => useFormData({ settings: { theme: 'dark' } }))
    act(() => {
      result.current.updateNested('settings', 'theme', 'light')
    })
    expect(result.current.formData.settings.theme).toBe('light')
  })

  it('resetForm restores initial values', () => {
    const initial = { name: 'original' }
    const { result } = renderHook(() => useFormData(initial))
    act(() => {
      result.current.updateField('name', 'changed')
    })
    expect(result.current.formData.name).toBe('changed')
    act(() => {
      result.current.resetForm()
    })
    expect(result.current.formData.name).toBe('original')
  })
})


// ════════════════════════════════════════════════════════════════════
// useModals Hook Tests
// ════════════════════════════════════════════════════════════════════
describe('useModals', () => {
  it('initializes all modals as closed', () => {
    const { result } = renderHook(() => useModals(['create', 'edit', 'delete']))
    expect(result.current.modals).toEqual({ create: false, edit: false, delete: false })
  })

  it('open() sets modal to true', () => {
    const { result } = renderHook(() => useModals(['create', 'edit']))
    act(() => {
      result.current.open('create')
    })
    expect(result.current.modals.create).toBe(true)
    expect(result.current.modals.edit).toBe(false)
  })

  it('close() sets modal to false', () => {
    const { result } = renderHook(() => useModals(['create']))
    act(() => {
      result.current.open('create')
    })
    expect(result.current.modals.create).toBe(true)
    act(() => {
      result.current.close('create')
    })
    expect(result.current.modals.create).toBe(false)
  })
})


// ════════════════════════════════════════════════════════════════════
// usePermission Hook Tests
// ════════════════════════════════════════════════════════════════════
vi.mock('../../contexts/AuthContext', () => ({
  useAuth: vi.fn(),
}))

import { useAuth } from '../../contexts/AuthContext'
import { usePermission } from '../../hooks/usePermission'

describe('usePermission', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('admin with * has all permissions', () => {
    useAuth.mockReturnValue({ permissions: ['*'] })
    const { result } = renderHook(() => usePermission())
    expect(result.current.hasPermission('read:certificates')).toBe(true)
    expect(result.current.isAdmin()).toBe(true)
  })

  it('user with specific permissions can only do those', () => {
    useAuth.mockReturnValue({ permissions: ['read:certificates', 'read:cas'] })
    const { result } = renderHook(() => usePermission())
    expect(result.current.canRead('certificates')).toBe(true)
    expect(result.current.canWrite('certificates')).toBe(false)
    expect(result.current.isAdmin()).toBe(false)
  })

  it('wildcard category permissions work', () => {
    useAuth.mockReturnValue({ permissions: ['read:*'] })
    const { result } = renderHook(() => usePermission())
    expect(result.current.canRead('certificates')).toBe(true)
    expect(result.current.canRead('cas')).toBe(true)
    expect(result.current.canWrite('certificates')).toBe(false)
  })

  it('empty permissions deny everything', () => {
    useAuth.mockReturnValue({ permissions: [] })
    const { result } = renderHook(() => usePermission())
    expect(result.current.hasPermission('read:certificates')).toBe(false)
  })

  it('null permission required returns true', () => {
    useAuth.mockReturnValue({ permissions: [] })
    const { result } = renderHook(() => usePermission())
    expect(result.current.hasPermission(null)).toBe(true)
    expect(result.current.hasPermission('')).toBe(true)
  })
})


// ════════════════════════════════════════════════════════════════════
// useFavorites Hook Tests
// ════════════════════════════════════════════════════════════════════
import { useFavorites } from '../../hooks/useFavorites'

describe('useFavorites', () => {
  beforeEach(() => {
    localStorage.clear()
  })

  it('starts with empty favorites', () => {
    const { result } = renderHook(() => useFavorites('certificates'))
    expect(result.current.favorites).toEqual([])
  })

  it('toggleFavorite adds an item', () => {
    const { result } = renderHook(() => useFavorites('certificates'))
    act(() => {
      result.current.toggleFavorite({ id: 1, name: 'Test Cert' })
    })
    expect(result.current.favorites).toHaveLength(1)
    expect(result.current.isFavorite(1)).toBe(true)
  })

  it('toggleFavorite removes an existing item', () => {
    const { result } = renderHook(() => useFavorites('certificates'))
    act(() => {
      result.current.toggleFavorite({ id: 1, name: 'Test Cert' })
    })
    expect(result.current.isFavorite(1)).toBe(true)
    act(() => {
      result.current.toggleFavorite({ id: 1, name: 'Test Cert' })
    })
    expect(result.current.isFavorite(1)).toBe(false)
  })

  it('persists to localStorage', () => {
    const { result } = renderHook(() => useFavorites('cas'))
    act(() => {
      result.current.toggleFavorite({ id: 5, name: 'Root CA' })
    })
    const stored = JSON.parse(localStorage.getItem('ucm-favorites'))
    expect(stored.cas).toHaveLength(1)
    expect(stored.cas[0].id).toBe(5)
  })

  it('different types are independent', () => {
    const { result: certResult } = renderHook(() => useFavorites('certificates'))
    const { result: caResult } = renderHook(() => useFavorites('cas'))
    act(() => {
      certResult.current.toggleFavorite({ id: 1, name: 'Cert' })
    })
    expect(certResult.current.favorites).toHaveLength(1)
    expect(caResult.current.favorites).toHaveLength(0)
  })
})


// ════════════════════════════════════════════════════════════════════
// useAutoPageSize Hook Tests
// ════════════════════════════════════════════════════════════════════
import { useAutoPageSize } from '../../hooks/useAutoPageSize'

describe('useAutoPageSize', () => {
  it('returns an object with perPage', () => {
    const { result } = renderHook(() => useAutoPageSize())
    expect(typeof result.current.perPage).toBe('number')
    expect(result.current.perPage).toBeGreaterThan(0)
  })

  it('returns containerRef', () => {
    const { result } = renderHook(() => useAutoPageSize())
    expect(result.current.containerRef).toBeDefined()
  })

  it('defaults to defaultPerPage option', () => {
    const { result } = renderHook(() => useAutoPageSize({ defaultPerPage: 25 }))
    expect(result.current.perPage).toBe(25)
  })

  it('setPerPage overrides auto mode', () => {
    const { result } = renderHook(() => useAutoPageSize({ defaultPerPage: 20 }))
    act(() => {
      result.current.setPerPage(50)
    })
    expect(result.current.perPage).toBe(50)
    expect(result.current.autoMode).toBe(false)
  })
})
