/**
 * Destructive actions ask first, through one mechanism (DUP-FE-008).
 *
 * Three ways of confirming coexisted: showConfirm from NotificationContext
 * (the majority, ~54 call sites), the ConfirmModal component (~10), and one
 * lone window.confirm. The duplication was not free — ConfirmModal reads
 * `confirmLabel` while showConfirm takes `confirmText`, and four dialogs in
 * SettingsPage passed the wrong one, so their button read the component's
 * hardcoded English default instead of "Delete" or "Disable encryption".
 *
 * Meanwhile a handful of handlers went straight to the API: rotating a SCEP
 * challenge (every enrolled device stops enrolling), denying a request on a
 * remote Microsoft CA (applied there, audited there, not undoable here),
 * deleting a stored ACME CA account (its account key is gone), and dropping a
 * CA's delegated OCSP responder (live responses change signer at once).
 */
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { readFileSync } from 'node:fs'
import { join } from 'node:path'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const scepMocks = vi.hoisted(() => ({
  regenerateProfileChallenge: vi.fn(),
  deleteProfile: vi.fn(),
}))
const mscaMocks = vi.hoisted(() => ({
  caHealth: vi.fn(),
  caPending: vi.fn(),
  denyRequest: vi.fn(),
  approveRequest: vi.fn(),
}))
const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, fallback) => (typeof fallback === 'string' ? fallback : key),
    i18n: { language: 'en', changeLanguage: vi.fn(), on: vi.fn(), off: vi.fn() },
  }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))

vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))

vi.mock('../../services', () => ({
  scepService: scepMocks,
  mscaService: mscaMocks,
}))

import { MscaCaControlModal } from '../MscaCaControlModal'


beforeEach(() => {
  Object.values(notify).forEach(fn => fn.mockReset())
  Object.values(scepMocks).forEach(fn => fn.mockReset())
  Object.values(mscaMocks).forEach(fn => fn.mockReset())
  scepMocks.regenerateProfileChallenge.mockResolvedValue({ data: { challenge: 'new-secret' } })
  scepMocks.deleteProfile.mockResolvedValue({})
  mscaMocks.caHealth.mockResolvedValue({ data: { certsvc_status: 'Running' } })
  mscaMocks.caPending.mockResolvedValue({
    data: [{ request_id: 17, subject_cn: 'kiosk-4', requester_name: 'DOM\\svc', template: 'Machine', submitted_when: 'today' }],
  })
  mscaMocks.denyRequest.mockResolvedValue({})
})

// SCEP profiles: rotation waits for the mockup's dialog and deletion goes through showConfirm
// (pages/__tests__/SCEPPage.atelier.test.jsx).

describe('denying a request on a Microsoft CA asks first', () => {
  const renderModal = () => render(
    <MscaCaControlModal connection={{ id: 5, name: 'Corp CA' }} open onClose={vi.fn()} />
  )

  it('does not deny when the operator declines', async () => {
    notify.showConfirm.mockResolvedValue(false)
    renderModal()
    fireEvent.click(await screen.findByText('msca.deny'))

    await waitFor(() => expect(notify.showConfirm).toHaveBeenCalledTimes(1))
    expect(mscaMocks.denyRequest).not.toHaveBeenCalled()
  })

  it('denies once the operator accepts', async () => {
    notify.showConfirm.mockResolvedValue(true)
    renderModal()
    fireEvent.click(await screen.findByText('msca.deny'))

    await waitFor(() => expect(mscaMocks.denyRequest).toHaveBeenCalledWith(5, 17))
  })
})

// The remaining surfaces live inside pages too large to drive here; these read
// the source instead, which is enough to catch the guard being removed.
const SRC = join(__dirname, '..', '..')
const read = (rel) => readFileSync(join(SRC, rel), 'utf8')

/** The body of `const <name> = ...` up to its matching closing brace. */
function handlerBody(source, name) {
  const start = source.indexOf(`const ${name} =`)
  if (start === -1) throw new Error(`handler ${name} not found`)
  const open = source.indexOf('{', start)
  let depth = 0
  for (let i = open; i < source.length; i++) {
    if (source[i] === '{') depth++
    else if (source[i] === '}' && --depth === 0) return source.slice(open, i + 1)
  }
  throw new Error(`handler ${name} is unbalanced`)
}

describe('the remaining destructive handlers confirm before calling the API', () => {
  it.each([
    ['pages/CRLOCSPPage.jsx', 'handleRemoveResponder'],
    ['pages/ACMEPage.jsx', 'handleDeleteCaAccount'],
    ['pages/SCEPPage.jsx', 'regenerateCaChallenge'],
  ])('%s → %s', (file, handler) => {
    const body = handlerBody(read(file), handler)
    expect(body).toContain('showConfirm')
    expect(body).toMatch(/if \(!confirmed\) return/)
    // The guard has to come first, not decorate a request already sent.
    const bail = body.indexOf('if (!confirmed) return')
    const call = body.search(/await\s+\w+Service\./)
    expect(call, `${handler} makes no service call`).toBeGreaterThan(-1)
    expect(bail).toBeLessThan(call)
  })
})

describe('one confirmation mechanism, spelled one way', () => {
  const PAGES = ['pages/SettingsPage.jsx', 'pages/DiscoveryPage.jsx', 'pages/OperationsPage.jsx',
    'pages/settings/DatabaseBackendSection.jsx']

  it('never hands ConfirmModal the option name showConfirm uses', () => {
    // ConfirmModal reads confirmLabel; confirmText silently falls back to the
    // component default, which is untranslated English.
    for (const file of PAGES) {
      const source = read(file)
      const blocks = source.split('<ConfirmModal').slice(1)
      for (const block of blocks) {
        const props = block.slice(0, block.indexOf('/>'))
        expect(props, `${file}: <ConfirmModal> got confirmText`).not.toContain('confirmText')
      }
    }
  })

  it('leaves no raw window.confirm anywhere in the app', () => {
    const offenders = []
    const files = [
      'pages/scep/ScepProfileForm.jsx', 'pages/SCEPPage.jsx', 'pages/CRLOCSPPage.jsx',
      'pages/ACMEPage.jsx', 'components/MscaCaControlModal.jsx',
    ]
    for (const file of files) {
      if (/\bwindow\.confirm\s*\(/.test(read(file))) offenders.push(file)
    }
    expect(offenders).toEqual([])
  })
})
