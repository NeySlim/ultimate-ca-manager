import { describe, expect, it, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, options) => (options && options.defaultValue !== undefined ? `${key}|${options.defaultValue}` : key),
  }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Badge: ({ children, variant }) => <span data-variant={variant}>{children}</span>,
  DetailSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
}))

const getFipsPreflight = vi.fn()
vi.mock('../../../services', () => ({
  systemService: { getFipsPreflight: (...args) => getFipsPreflight(...args) },
}))

import FipsPreflightPanel from '../FipsPreflightPanel'

const finding = (id, severity, extra = {}) => ({
  id, severity, title: `title of ${id}`, remedy: `remedy of ${id}`,
  count: 1, examples: [`example of ${id}`], ...extra,
})

describe('FipsPreflightPanel', () => {
  beforeEach(() => getFipsPreflight.mockReset())

  it('runs the check only when asked, then shows the findings grouped by severity', async () => {
    getFipsPreflight.mockResolvedValue({ data: {
      ready: false,
      summary: { blocker: 1, warning: 1, info: 1 },
      findings: [
        finding('users.password_scrypt', 'blocker', { count: 7, examples: ['alice (#1)'] }),
        finding('hsm.softhsm', 'warning'),
        finding('certificates.unapproved_key', 'info'),
      ],
      errors: [],
    } })
    render(<FipsPreflightPanel />)
    expect(getFipsPreflight).not.toHaveBeenCalled()

    fireEvent.click(screen.getByText('settings.fipsPreflight.run'))
    const report = await screen.findByTestId('fips-preflight-report')

    expect(getFipsPreflight).toHaveBeenCalledOnce()
    expect(within(report).getByText('settings.fipsPreflight.notReady')).toBeInTheDocument()
    expect(within(report).getByText(
      'settings.fipsPreflight.checks.users_password_scrypt.title|title of users.password_scrypt',
    )).toBeInTheDocument()
    expect(within(report).getByText('alice (#1)')).toBeInTheDocument()
    expect(within(report).getByText('settings.fipsPreflight.more')).toBeInTheDocument()
    expect(within(report).getByText(
      'settings.fipsPreflight.checks.users_password_scrypt.remedy|remedy of users.password_scrypt',
    )).toBeInTheDocument()

    const headings = within(report).getAllByRole('heading', { level: 4 }).map((h) => h.textContent)
    expect(headings).toEqual([
      'settings.fipsPreflight.severity.blocker',
      'settings.fipsPreflight.severity.warning',
      'settings.fipsPreflight.severity.info',
    ])
  })

  it('says when nothing blocks', async () => {
    getFipsPreflight.mockResolvedValue({ data: {
      ready: true, summary: { blocker: 0, warning: 0, info: 0 }, findings: [], errors: [],
    } })
    render(<FipsPreflightPanel />)
    fireEvent.click(screen.getByText('settings.fipsPreflight.run'))
    expect(await screen.findByText('settings.fipsPreflight.ready')).toBeInTheDocument()
    expect(screen.getByText('settings.fipsPreflight.nothingFound')).toBeInTheDocument()
  })

  it('names a check that could not run and a request that failed', async () => {
    getFipsPreflight.mockResolvedValueOnce({ data: {
      ready: false, summary: { blocker: 0, warning: 0, info: 0 }, findings: [],
      errors: [{ id: 'users.password_scrypt', error: 'OperationalError' }],
    } })
    render(<FipsPreflightPanel />)
    fireEvent.click(screen.getByText('settings.fipsPreflight.run'))
    expect(await screen.findByText('settings.fipsPreflight.checkFailed')).toBeInTheDocument()

    getFipsPreflight.mockRejectedValueOnce(new Error('Forbidden'))
    fireEvent.click(screen.getByText('settings.fipsPreflight.run'))
    await waitFor(() => expect(screen.getByText('Forbidden')).toBeInTheDocument())
    expect(screen.queryByTestId('fips-preflight-report')).not.toBeInTheDocument()
  })
})
