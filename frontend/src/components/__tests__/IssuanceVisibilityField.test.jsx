/**
 * A CA hidden from the issuance pickers (#430): the details show the state and
 * switch it both ways, only with write:cas; a picker lists a hidden CA behind
 * its link, or when it is already chosen.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

const mocks = vi.hoisted(() => ({
  update: vi.fn(),
  showSuccess: vi.fn(),
  showError: vi.fn(),
  onChanged: vi.fn(),
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
  useNotification: () => ({ showSuccess: mocks.showSuccess, showError: mocks.showError }),
}))
vi.mock('../../services', () => ({ casService: { update: mocks.update } }))

import { IssuanceVisibilityField } from '../cas/IssuanceVisibilityField'
import { HiddenCasToggle } from '../cas/HiddenCasToggle'
import { hiddenFromIssuance, listedForIssuance, pickerCas, signingCas } from '../../lib/caSelection'

const listed = { id: 1, refid: 'r-1', descr: 'Issuing CA', has_private_key: true, issuance_hidden: false }
const root = { id: 2, refid: 'r-2', descr: 'Root CA', has_private_key: true, issuance_hidden: true }
const keylessHidden = { id: 3, descr: 'Old root', has_private_key: false, certificate_only: true, issuance_hidden: true }

beforeEach(() => vi.clearAllMocks())

describe('issuance pickers', () => {
  it('leave a hidden CA out until asked, and count only the ones that can sign', () => {
    const cas = [listed, root, keylessHidden]
    expect(listedForIssuance(signingCas(cas), false)).toEqual([listed])
    expect(listedForIssuance(signingCas(cas), true)).toEqual([listed, root])
    expect(hiddenFromIssuance(signingCas(cas))).toBe(1)
  })

  it('keep listing a hidden CA already chosen, by id or by refid, and stop counting it', () => {
    expect(listedForIssuance([listed, root], false, '2')).toEqual([listed, root])
    expect(listedForIssuance([listed, root], false, 'r-2')).toEqual([listed, root])
    expect(hiddenFromIssuance([listed, root], 'r-2')).toBe(0)
  })

  it('apply to the mTLS pickers, which keep a chosen CA that can no longer sign', () => {
    const cas = [listed, root, keylessHidden]
    expect(listedForIssuance(pickerCas(cas, 'r-1'), false, 'r-1')).toEqual([listed])
    expect(listedForIssuance(pickerCas(cas, 3), false, 3)).toEqual([listed, keylessHidden])
  })

  it('show the link only when a CA is hidden, and toggle it', () => {
    const onToggle = vi.fn()
    const { rerender, container } = render(<HiddenCasToggle count={0} shown={false} onToggle={onToggle} />)
    expect(container).toBeEmptyDOMElement()
    rerender(<HiddenCasToggle count={2} shown={false} onToggle={onToggle} />)
    fireEvent.click(screen.getByText('cas.showHiddenCas:2'))
    expect(onToggle).toHaveBeenCalledTimes(1)
    rerender(<HiddenCasToggle count={2} shown onToggle={onToggle} />)
    expect(screen.getByText('cas.hideHiddenCas')).toBeInTheDocument()
  })
})

describe('IssuanceVisibilityField', () => {
  it('hides a listed CA', async () => {
    mocks.update.mockResolvedValue({ data: { ...listed, issuance_hidden: true } })
    render(<IssuanceVisibilityField ca={listed} canWrite onChanged={mocks.onChanged} />)
    expect(screen.getByText('cas.issuanceListedState')).toBeInTheDocument()
    fireEvent.click(screen.getByText('cas.hideFromIssuance'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(1, { issuanceHidden: true }))
    await waitFor(() => expect(mocks.onChanged).toHaveBeenCalledWith({ ...listed, issuance_hidden: true }))
    expect(mocks.showSuccess).toHaveBeenCalledWith('cas.issuanceVisibilityChanged')
  })

  it('lists a hidden CA again', async () => {
    mocks.update.mockResolvedValue({ data: { ...root, issuance_hidden: false } })
    render(<IssuanceVisibilityField ca={root} canWrite onChanged={mocks.onChanged} />)
    expect(screen.getByText('cas.issuanceHiddenState')).toBeInTheDocument()
    fireEvent.click(screen.getByText('cas.showInIssuance'))
    await waitFor(() => expect(mocks.update).toHaveBeenCalledWith(2, { issuanceHidden: false }))
  })

  it('reports a refusal', async () => {
    mocks.update.mockRejectedValue(new Error('issuanceHidden must be true or false'))
    render(<IssuanceVisibilityField ca={listed} canWrite />)
    fireEvent.click(screen.getByText('cas.hideFromIssuance'))
    await waitFor(() => expect(mocks.showError).toHaveBeenCalledWith('issuanceHidden must be true or false'))
  })

  it('offers no switch without write:cas', () => {
    render(<IssuanceVisibilityField ca={listed} />)
    expect(screen.getByText('cas.issuanceListedState')).toBeInTheDocument()
    expect(screen.queryByText('cas.hideFromIssuance')).toBeNull()
  })
})
