/**
 * The CA option enforce_unique_subject: shown with its help, switched both ways with write:cas,
 * the subjects already shared counted when it is turned on.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  update: vi.fn(), showSuccess: vi.fn(), showWarning: vi.fn(), showError: vi.fn(), onChanged: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts?.count !== undefined ? `${key}:${opts.count}` : key),
    i18n: { language: 'en' },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))
vi.mock('../../contexts/NotificationContext', () => ({
  useNotification: () => ({ showSuccess: mocks.showSuccess, showWarning: mocks.showWarning, showError: mocks.showError }),
}))
vi.mock('../../services', () => ({ casService: { update: mocks.update } }))

import { UniqueSubjectField } from '../cas/UniqueSubjectField'

const off = { id: 1, descr: 'Issuing CA', enforce_unique_subject: false }
const on = { ...off, enforce_unique_subject: true }

beforeEach(() => vi.clearAllMocks())

describe('UniqueSubjectField', () => {
  it('turns it on and says how many subjects are already shared', async () => {
    mocks.update.mockResolvedValue({ data: { ...on, shared_subjects: 3 } })
    render(<UniqueSubjectField ca={off} canWrite onChanged={mocks.onChanged} />)
    expect(screen.getByText('cas.uniqueSubjectNotEnforced')).toBeInTheDocument()
    expect(screen.getAllByText('cas.uniqueSubjectHelp').length).toBeGreaterThan(0)
    fireEvent.click(screen.getByText('cas.enforceUniqueSubject'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(1, { enforceUniqueSubject: true }))
    await waitFor(() => expect(mocks.showWarning).toHaveBeenCalledWith('cas.uniqueSubjectShared:3'))
    expect(mocks.onChanged).toHaveBeenCalledWith({ ...on, shared_subjects: 3 })
  })

  it('turns it off without a warning', async () => {
    mocks.update.mockResolvedValue({ data: off })
    render(<UniqueSubjectField ca={on} canWrite onChanged={mocks.onChanged} />)
    expect(screen.getByText('cas.uniqueSubjectEnforced')).toBeInTheDocument()
    fireEvent.click(screen.getByText('cas.stopEnforcingUniqueSubject'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(1, { enforceUniqueSubject: false }))
    expect(mocks.showWarning).not.toHaveBeenCalled()
  })

  it('reports a refusal', async () => {
    mocks.update.mockRejectedValue(new Error('enforceUniqueSubject must be true or false'))
    render(<UniqueSubjectField ca={off} canWrite />)
    fireEvent.click(screen.getByText('cas.enforceUniqueSubject'))
    await waitFor(() => expect(mocks.showError).toHaveBeenCalledWith('enforceUniqueSubject must be true or false'))
  })

  it('offers no switch without write:cas', () => {
    render(<UniqueSubjectField ca={on} />)
    expect(screen.queryByText('cas.stopEnforcingUniqueSubject')).toBeNull()
  })
})
