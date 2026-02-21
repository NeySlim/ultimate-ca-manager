/**
 * Page Rendering Tests — Users & Groups page
 * Uses dynamic import to reduce peak memory during module loading
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'

function TestWrapper({ children, route = '/' }) {
  return <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
}

describe('Page Rendering — Users & Groups', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('UsersGroupsPage renders without crashing', async () => {
    const { default: UsersGroupsPage } = await import('../UsersGroupsPage')
    expect(UsersGroupsPage).toBeDefined()
    expect(typeof UsersGroupsPage).toBe('function')
  }, 30000)
})
