/**
 * Page Rendering Tests — Audit Logs page
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import './pageRenderingSetup.jsx'

import AuditLogsPage from '../AuditLogsPage'

function TestWrapper({ children, route = '/' }) {
  return <MemoryRouter initialEntries={[route]}>{children}</MemoryRouter>
}

describe('Page Rendering — Audit', () => {
  beforeEach(() => { vi.clearAllMocks() })

  it('AuditLogsPage renders without crashing', () => {
    const { container } = render(<TestWrapper route="/audit-logs"><AuditLogsPage /></TestWrapper>)
    expect(container.firstChild).toBeTruthy()
  })
})
