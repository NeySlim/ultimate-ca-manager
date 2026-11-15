import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, vars) => (vars ? `${key} ${JSON.stringify(vars)}` : key) }),
}))
vi.mock('../../../components', () => ({
  Modal: ({ open, title, children }) => (open ? <div role="dialog"><h2>{title}</h2>{children}</div> : null),
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
}))

import RestoreReport from '../RestoreReport'

const reload = vi.fn()
beforeEach(() => {
  vi.useFakeTimers()
  vi.stubGlobal('location', { ...window.location, reload })
})
afterEach(() => {
  vi.useRealTimers()
  vi.unstubAllGlobals()
  reload.mockClear()
})

const show = (data) => render(
  <MemoryRouter><RestoreReport data={data} onClose={vi.fn()} /></MemoryRouter>
)

describe('RestoreReport', () => {
  it('lists every warning, one per line, and does not reload', () => {
    show({
      users: 2, cas: 1, certificates: 5, restart_requested: true,
      todo: ['No new CRL could be signed for: Root CA', 'Section not restored by this version: hsm_providers'],
    })
    expect(screen.getByText('No new CRL could be signed for: Root CA')).toBeTruthy()
    expect(screen.getByText('Section not restored by this version: hsm_providers')).toBeTruthy()
    act(() => { vi.advanceTimersByTime(10000) })
    expect(reload).not.toHaveBeenCalled()
  })

  it('reloads on close when there were warnings', () => {
    show({ todo: ['x'], restart_requested: false, restart_detail: 'restart it' })
    fireEvent.click(screen.getByRole('button', { name: 'common.close' }))
    expect(reload).toHaveBeenCalled()
  })

  it('without warnings keeps the simple success and reloads after two seconds', () => {
    show({ users: 2, cas: 1, certificates: 5, todo: [], restart_requested: true })
    expect(screen.queryByText('settings.restoreReportTodo')).toBeNull()
    act(() => { vi.advanceTimersByTime(2000) })
    expect(reload).toHaveBeenCalled()
  })
})
