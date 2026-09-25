import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

let mockIsMobile = false
let readable = () => true
const openWindow = vi.fn()
const navigate = vi.fn()

vi.mock('react-router-dom', async () => ({
  ...(await vi.importActual('react-router-dom')),
  useNavigate: () => navigate,
}))
vi.mock('../../contexts', () => ({
  useMobile: () => ({ isMobile: mockIsMobile }),
  useWindowManager: () => ({ openWindow }),
}))
vi.mock('..', () => ({
  usePermission: () => ({ canRead: (resource) => readable(resource) }),
}))

import { useOpenEntity } from '../useOpenEntity'

const open = () => renderHook(() => useOpenEntity(), { wrapper: MemoryRouter }).result.current

describe('useOpenEntity', () => {
  beforeEach(() => {
    mockIsMobile = false
    readable = () => true
    openWindow.mockClear()
    navigate.mockClear()
  })

  it('opens a floating window on desktop', () => {
    open()('ca', 5)
    expect(openWindow).toHaveBeenCalledWith('ca', 5)
    expect(navigate).not.toHaveBeenCalled()
  })

  it('follows the deep link on mobile, where windows are not shown', () => {
    mockIsMobile = true
    open()('truststore', 3)
    expect(navigate).toHaveBeenCalledWith('/truststore/3')
    expect(openWindow).not.toHaveBeenCalled()
  })

  it('opens nothing the user cannot read', () => {
    readable = (resource) => resource !== 'certificates'
    open()('certificate', 8)
    expect(openWindow).not.toHaveBeenCalled()
    open()('ca', 8)
    expect(openWindow).toHaveBeenCalledWith('ca', 8)
  })

  it('opens nothing without an id or for a type with no detail', () => {
    open()('certificate', undefined)
    open()('csr', 4)
    expect(openWindow).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })
})
