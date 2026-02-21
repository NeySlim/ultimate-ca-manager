/**
 * Page Rendering Tests — Settings page (isolated due to large size)
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'

import SettingsPage from '../SettingsPage'

function TestWrapper({ children, route = '/' }) {
  return <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
}

describe('Page Rendering — Settings', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('SettingsPage renders without crashing', () => {
    const { container } = render(<TestWrapper route="/settings"><SettingsPage /></TestWrapper>)
    expect(container.firstChild).toBeTruthy()
  })
})
