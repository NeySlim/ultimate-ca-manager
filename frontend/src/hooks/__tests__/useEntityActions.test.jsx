/**
 * useEntityActions: which actions an entity offers, to whom, and what the
 * guarded ones do when a surface calls them anyway.
 */
import { renderHook, act, render, screen, fireEvent } from '@testing-library/react'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const notify = vi.hoisted(() => ({
  showSuccess: vi.fn(), showError: vi.fn(), showWarning: vi.fn(),
  showConfirm: vi.fn(), showPrompt: vi.fn(),
}))
const svc = vi.hoisted(() => ({
  certs: { delete: vi.fn(), revoke: vi.fn(), unhold: vi.fn(), export: vi.fn(), renew: vi.fn(), getById: vi.fn() },
  cas: { delete: vi.fn(), revoke: vi.fn(), export: vi.fn(), getById: vi.fn(), renewCsr: vi.fn(), downloadCsr: vi.fn() },
}))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
  Trans: ({ children }) => children,
  initReactI18next: { type: '3rdParty', init: () => {} },
}))
vi.mock('../../contexts', () => ({
  useNotification: () => notify,
  useMobile: () => ({ isMobile: false, isTablet: false }),
}))
vi.mock('../../contexts/AuthContext', () => ({ useAuth: () => ({ permissions: [] }) }))
vi.mock('../../services', () => ({
  certificatesService: svc.certs,
  casService: svc.cas,
  userCertificatesService: { delete: vi.fn(), revoke: vi.fn(), export: vi.fn() },
  truststoreService: { delete: vi.fn(), export: vi.fn() },
}))

import { useEntityActions } from '../useEntityActions'

const rights = (granted = [], scopes = []) => ({
  canWrite: (r) => granted.includes(`write:${r}`),
  canDelete: (r) => granted.includes(`delete:${r}`),
  hasPermission: (s) => scopes.includes(s),
})

const CERT = {
  id: 4, common_name: 'web.example.com', status: 'valid', revoked: false,
  has_private_key: true, valid_to: '2030-01-01T00:00:00Z',
}
const CA = {
  id: 9, common_name: 'Sub CA', type: 'intermediate', is_root: false, parent_id: 1,
  has_private_key: true, revoked: false, pending: false, offline: false,
}

const run = (type, entity, permissions, extra = {}) =>
  renderHook(() => useEntityActions({ type, entity, permissions, onClose: vi.fn(), ...extra })).result.current

const visible = (r) => r.actions.filter(a => a.visible && a.inBar !== false).map(a => a.id)

beforeEach(() => vi.clearAllMocks())

describe('certificate actions by permission', () => {
  it('hides revocation from a principal without write:certificates', () => {
    expect(visible(run('certificate', CERT, rights()))).not.toContain('revoke')
    expect(visible(run('certificate', CERT, rights(['write:certificates'])))).toContain('revoke')
  })

  it('offers Remove Hold only to a certificate that is on hold', () => {
    const w = rights(['write:certificates'])
    expect(visible(run('certificate', CERT, w))).not.toContain('unhold')
    const held = { ...CERT, revoked: true, revoke_reason: 'certificateHold', status: 'revoked' }
    expect(visible(run('certificate', held, w))).toContain('unhold')
    const revoked = { ...CERT, revoked: true, revoke_reason: 'keyCompromise', status: 'revoked' }
    expect(visible(run('certificate', revoked, w))).not.toContain('unhold')
  })

  it('offers recovery of an archived key only with write:key_recovery', () => {
    expect(visible(run('certificate', CERT, rights()))).not.toContain('keyRecovery')
    expect(visible(run('certificate', CERT, rights([], ['write:key_recovery'])))).toContain('keyRecovery')
  })

  it('offers delete on the resource of the type, not on certificates', () => {
    expect(visible(run('truststore', { id: 1, name: 'root' }, rights(['delete:certificates'])))).not.toContain('delete')
    expect(visible(run('truststore', { id: 1, name: 'root' }, rights(['delete:truststore'])))).toContain('delete')
  })
})

describe('key export', () => {
  const open = (permissions) => {
    function Probe() {
      const { actions, modals } = useEntityActions({ type: 'certificate', entity: CERT, permissions, onClose: vi.fn() })
      return <>{actions.find(a => a.id === 'export').label}<button onClick={actions.find(a => a.id === 'export').onClick}>go</button>{modals}</>
    }
    render(<Probe />)
    fireEvent.click(screen.getByText('go'))
  }

  it('hides key formats without read:private_keys', () => {
    open(rights(['write:certificates']))
    expect(screen.queryByText('P12 / PKCS#12')).toBeNull()
    expect(screen.getByText('PEM')).toBeInTheDocument()
  })

  it('offers them with read:private_keys', () => {
    open(rights(['write:certificates'], ['read:private_keys']))
    expect(screen.getByText('P12 / PKCS#12')).toBeInTheDocument()
  })
})

describe('CA actions', () => {
  it('shows key import only for a CA that holds no key, and offline only for one that does', () => {
    const w = rights(['write:cas'])
    const withKey = run('ca', CA, w)
    expect(withKey.handler('importKey')).toBeNull()
    expect(withKey.handler('offline')).toBeTypeOf('function')
    const noKey = run('ca', { ...CA, has_private_key: false, certificate_only: true }, w)
    expect(noKey.handler('importKey')).toBeTypeOf('function')
    expect(noKey.handler('offline')).toBeNull()
  })

  it('keeps key import out of the action bar', () => {
    expect(visible(run('ca', { ...CA, has_private_key: false, certificate_only: true }, rights(['write:cas'])))).not.toContain('importKey')
  })

  it('revokes a root CA through no one: it has no parent to sign the revocation', () => {
    const root = { ...CA, type: 'root', is_root: true, parent_id: null }
    expect(visible(run('ca', root, rights(['write:cas'])))).not.toContain('revoke')
  })

  it('offers pins only with both write:cas and write:templates', () => {
    expect(visible(run('ca', CA, rights(['write:cas'])))).not.toContain('pins')
    expect(visible(run('ca', CA, rights(['write:cas', 'write:templates'])))).toContain('pins')
  })
})

describe('delete guard', () => {
  it('sends nothing when a surface calls delete without delete rights', async () => {
    const r = run('certificate', { ...CERT, status: 'revoked', revoked: true }, rights(['write:certificates']))
    const del = r.actions.find(a => a.id === 'delete')
    expect(del.visible).toBe(false)
    await act(async () => { await del.onClick() })
    expect(notify.showConfirm).not.toHaveBeenCalled()
    expect(svc.certs.delete).not.toHaveBeenCalled()
  })

  it('deletes a revoked certificate after confirmation and closes the surface', async () => {
    notify.showConfirm.mockResolvedValueOnce(true)
    svc.certs.delete.mockResolvedValue({})
    const onClose = vi.fn()
    const r = run('certificate', { ...CERT, status: 'revoked', revoked: true }, rights(['delete:certificates']), { onClose })
    await act(async () => { await r.actions.find(a => a.id === 'delete').onClick() })
    expect(svc.certs.delete).toHaveBeenCalledWith(4)
    expect(onClose).toHaveBeenCalled()
  })
})

describe('what a surface does after an action', () => {
  const caRevoked = { id: 9, revoked: true, common_name: 'Sub CA' }
  const confirmRevoke = async (type, entity, extra) => {
    const onChanged = vi.fn(); const onClose = vi.fn()
    let api
    function Probe() {
      api = useEntityActions({ type, entity, permissions: rights(['write:cas', 'write:certificates']), onChanged, onClose, ...extra })
      return null
    }
    render(<Probe />)
    // the confirm handler is what the revoke modal calls
    const modalEl = api.modals.props.children.find(c => c?.props?.onConfirm)
    await act(async () => { await modalEl.props.onConfirm('keyCompromise', {}) })
    return { onChanged, onClose }
  }

  it('keeps a slide-over open after revoking a CA and hands it the revoked CA', async () => {
    svc.cas.revoke.mockResolvedValue({ data: caRevoked })
    svc.cas.getById.mockResolvedValue({ data: caRevoked })
    const { onChanged, onClose } = await confirmRevoke('ca', CA, { afterMutation: 'refresh' })
    expect(onClose).not.toHaveBeenCalled()
    expect(onChanged).toHaveBeenCalledWith(expect.objectContaining({ id: 9, revoked: true }))
  })

  it('warns with the server message when the issuing CA was not told of the revocation', async () => {
    const message = 'Certificate revoked in UCM only: the ACME CA was not notified'
    svc.certs.revoke.mockResolvedValue({ data: { ...CERT, revoked: true }, message, meta: { acme_local_only: true } })
    svc.certs.getById.mockResolvedValue({ data: { ...CERT, revoked: true } })
    await confirmRevoke('certificate', CERT)
    expect(notify.showWarning).toHaveBeenCalledWith(message)
    expect(notify.showSuccess).not.toHaveBeenCalledWith('messages.success.other.revoked')
  })

  it('closes the detail window after revoking a CA, as it always did', async () => {
    svc.cas.revoke.mockResolvedValue({ data: caRevoked })
    const { onClose } = await confirmRevoke('ca', CA)
    expect(onClose).toHaveBeenCalled()
  })

  it('closes the detail window after removing a hold and keeps a slide-over open', async () => {
    notify.showConfirm.mockResolvedValue(true)
    svc.certs.unhold.mockResolvedValue({})
    svc.certs.getById.mockResolvedValue({ data: { ...CERT, revoked: false } })
    const held = { ...CERT, revoked: true, revoke_reason: 'certificateHold', status: 'revoked' }
    const w = rights(['write:certificates'])
    const onClose = vi.fn(); const onChanged = vi.fn()
    const win = run('certificate', held, w, { onClose })
    await act(async () => { await win.handler('unhold')() })
    expect(onClose).toHaveBeenCalled()
    const onClose2 = vi.fn()
    const so = run('certificate', held, w, { onClose: onClose2, onChanged, afterMutation: 'refresh' })
    await act(async () => { await so.handler('unhold')() })
    expect(onClose2).not.toHaveBeenCalled()
    expect(onChanged).toHaveBeenCalled()
  })

  it('names the linked certificate when removing a hold lifts it too', async () => {
    notify.showConfirm.mockResolvedValue(true)
    svc.certs.unhold.mockResolvedValue({ data: { related_unheld: 8 } })
    svc.certs.getById.mockResolvedValue({ data: { ...CERT, revoked: false } })
    const held = { ...CERT, revoked: true, revoke_reason: 'certificateHold', status: 'revoked', related_certificate_id: 8 }
    const r = run('certificate', held, rights(['write:certificates']), { onClose: vi.fn() })
    await act(async () => { await r.handler('unhold')() })
    expect(notify.showConfirm.mock.calls.at(-1)[0]).toBe('certificates.unholdWarningRelated')
    expect(notify.showSuccess).toHaveBeenLastCalledWith('certificates.unheldWithRelated')
  })

  it('keeps the single-certificate wording without a linked certificate', async () => {
    notify.showConfirm.mockResolvedValue(true)
    svc.certs.unhold.mockResolvedValue({ data: {} })
    svc.certs.getById.mockResolvedValue({ data: { ...CERT, revoked: false } })
    const held = { ...CERT, revoked: true, revoke_reason: 'certificateHold', status: 'revoked' }
    const r = run('certificate', held, rights(['write:certificates']), { onClose: vi.fn() })
    await act(async () => { await r.handler('unhold')() })
    expect(notify.showConfirm.mock.calls.at(-1)[0]).toBe('certificates.unholdWarning')
    expect(notify.showSuccess).toHaveBeenLastCalledWith('certificates.unheld')
  })

  it('closes after a delete even on a slide-over: the entity is gone', async () => {
    notify.showConfirm.mockResolvedValueOnce(true)
    svc.certs.delete.mockResolvedValue({})
    const onClose = vi.fn()
    const r = run('certificate', { ...CERT, status: 'revoked', revoked: true }, rights(['delete:certificates']), { onClose, afterMutation: 'refresh' })
    await act(async () => { await r.actions.find(a => a.id === 'delete').onClick() })
    expect(onClose).toHaveBeenCalled()
  })
})

describe('permissions override', () => {
  it('keeps the ambient function when a caller passes undefined for it', () => {
    const r = () => renderHook(() => useEntityActions({
      type: 'certificate', entity: CERT, permissions: { canWrite: undefined, canDelete: undefined, hasPermission: undefined }, onClose: vi.fn(),
    })).result.current
    expect(r().actions.length).toBeGreaterThan(0)
  })
})
