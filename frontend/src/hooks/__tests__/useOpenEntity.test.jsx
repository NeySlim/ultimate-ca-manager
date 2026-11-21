import { describe, it, expect, vi, beforeEach } from 'vitest'
import { renderHook } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

let readable = () => true
const openEntity = vi.fn()
const navigate = vi.fn()

vi.mock('react-router-dom', async () => ({
  ...(await vi.importActual('react-router-dom')),
  useNavigate: () => navigate,
}))
vi.mock('../../contexts', () => ({
  useInspector: () => ({ openEntity }),
}))
vi.mock('..', () => ({
  usePermission: () => ({ canRead: (resource) => readable(resource) }),
}))

import { useOpenEntity } from '../useOpenEntity'

const open = () => renderHook(() => useOpenEntity(), { wrapper: MemoryRouter }).result.current

describe('useOpenEntity', () => {
  beforeEach(() => {
    readable = () => true
    openEntity.mockClear()
    navigate.mockClear()
  })

  it('opens the inspector', () => {
    open()('ca', 5)
    expect(openEntity).toHaveBeenCalledWith('ca', 5)
    expect(navigate).not.toHaveBeenCalled()
  })

  it('hands the control to refocus on close to the inspector', () => {
    const origin = document.createElement('button')
    open()('truststore', 3, { origin })
    expect(openEntity).toHaveBeenCalledWith('truststore', 3, { origin })
    expect(navigate).not.toHaveBeenCalled()
  })

  it('opens nothing the user cannot read', () => {
    readable = (resource) => resource !== 'certificates'
    open()('certificate', 8)
    expect(openEntity).not.toHaveBeenCalled()
    open()('ca', 8)
    expect(openEntity).toHaveBeenCalledWith('ca', 8)
  })

  it('opens nothing without an id or for a type with no detail', () => {
    open()('certificate')
    open()('csr', 4)
    expect(openEntity).not.toHaveBeenCalled()
    expect(navigate).not.toHaveBeenCalled()
  })
})
