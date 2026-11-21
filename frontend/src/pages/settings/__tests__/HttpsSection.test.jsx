import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Badge: ({ children }) => <span>{children}</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
  DetailGrid: ({ children }) => <div>{children}</div>,
  DetailField: ({ label, value }) => <div>{label}{value}</div>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))

import HttpsSection from '../HttpsSection'

const renderSection = (httpsInfo, onUnbindHttpsCert = vi.fn()) => {
  render(
    <HttpsSection
      httpsInfo={httpsInfo}
      selectedHttpsCert={null}
      setSelectedHttpsCert={vi.fn()}
      setShowCertPicker={vi.fn()}
      handleApplyUcmCert={vi.fn()}
      handleRegenerateHttpsCert={vi.fn()}
      setShowHttpsImportModal={vi.fn()}
      onUnbindHttpsCert={onUnbindHttpsCert}
    />
  )
  return onUnbindHttpsCert
}

describe('HttpsSection bound certificate indicator (#303 follow-up)', () => {
  it('shows the bound certificate and triggers unbind', () => {
    const onUnbind = renderSection({
      type: 'CA-Signed',
      bound_certificate: { refid: 'ref-1', descr: 'Web UI cert', exists: true },
    })
    expect(screen.getByText(/settings\.httpsBound: Web UI cert/)).toBeInTheDocument()
    expect(screen.getByText('settings.httpsBoundDesc')).toBeInTheDocument()
    fireEvent.click(screen.getByText('settings.httpsUnbind'))
    expect(onUnbind).toHaveBeenCalled()
  })

  it('names the bound certificate by its CN with the description alongside (#365)', () => {
    renderSection({
      type: 'CA-Signed',
      bound_certificate: { refid: 'ref-1', common_name: 'ucm.example.com', descr: 'Web UI cert', exists: true },
    })
    expect(screen.getByText('settings.httpsBound: ucm.example.com · Web UI cert')).toBeInTheDocument()
  })

  it('makes the unbound state explicit', () => {
    renderSection({ type: 'Self-Signed' })
    expect(screen.getByText('settings.httpsNotBound')).toBeInTheDocument()
    expect(screen.queryByText('settings.httpsUnbind')).not.toBeInTheDocument()
  })

  it('says when a renewal left the binding on the previous certificate', () => {
    renderSection({
      type: 'CA-Signed',
      bound_certificate: { refid: 'ref-1', descr: 'Web UI cert', exists: true, needs_attention: {
        reason: 'successor_without_key', successor_id: 9, successor_refid: 'ref-2',
        successor_descr: 'Web UI cert', successor_has_key: false } },
    })
    expect(screen.getByText('settings.httpsLeftBehind')).toBeInTheDocument()
    expect(screen.getByText('settings.httpsLeftBehindNoKey')).toBeInTheDocument()
    expect(screen.queryByText('settings.httpsSelectRenewed')).not.toBeInTheDocument()
  })

  it('offers the renewed certificate once UCM holds its key', () => {
    const select = vi.fn()
    render(
      <HttpsSection
        httpsInfo={{ type: 'CA-Signed', bound_certificate: { refid: 'ref-1', exists: true, needs_attention: {
          reason: 'successor_without_key', successor_id: 9, successor_refid: 'ref-2',
          successor_descr: 'Web UI cert', successor_has_key: true } } }}
        selectedHttpsCert={null} setSelectedHttpsCert={select} setShowCertPicker={vi.fn()}
        handleApplyUcmCert={vi.fn()} handleRegenerateHttpsCert={vi.fn()}
        setShowHttpsImportModal={vi.fn()} onUnbindHttpsCert={vi.fn()}
      />
    )
    fireEvent.click(screen.getByText('settings.httpsSelectRenewed'))
    expect(select).toHaveBeenCalledWith(expect.objectContaining({ id: 9 }))
  })

  it('says the renewed certificate was superseded and offers no selection', () => {
    renderSection({
      type: 'CA-Signed',
      bound_certificate: { refid: 'ref-1', exists: true, needs_attention: {
        reason: 'successor_without_key', successor_id: 9, successor_refid: 'ref-2',
        successor_descr: 'Web UI cert', successor_has_key: true, successor_archived: true } },
    })
    expect(screen.getByText('settings.httpsLeftBehindSuperseded')).toBeInTheDocument()
    expect(screen.queryByText('settings.httpsSelectRenewed')).not.toBeInTheDocument()
  })
})
