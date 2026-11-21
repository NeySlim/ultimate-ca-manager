/**
 * CAs page, list view on a phone: each authority is a record with the facts of its row (type,
 * parent, certificates, algorithm, marks, state, expiry); the whole record opens its detail and
 * the chevron of the row stays at its right.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'

const screenSize = vi.hoisted(() => ({ isMobile: true }))
vi.mock('react-i18next', () => ({
  useTranslation: () => ({
    t: (key, opts) => (opts ? `${key}:${JSON.stringify(opts)}` : key),
    i18n: { language: 'en', changeLanguage: () => {} },
  }),
}))
vi.mock('../../../contexts', () => ({
  useMobile: () => ({ isMobile: screenSize.isMobile, isTablet: false, isDesktop: !screenSize.isMobile }),
}))

import { ListView } from '../ListView'
import { ca, smallHierarchy } from './caFixtures'

const t = (key, opts) => (opts ? `${key}:${JSON.stringify(opts)}` : key)
const record = (name) => screen.getAllByRole('listitem').find((li) => within(li).queryByRole('button', { name }))

beforeEach(() => {
  window.localStorage.clear()
  screenSize.isMobile = true
})

function renderList(cas = smallHierarchy()) {
  const onSelect = vi.fn()
  const onDownload = vi.fn()
  render(<ListView cas={cas} allCAs={cas} onSelect={onSelect} onDownload={onDownload} emptyTitle="none" t={t} />)
  return { onSelect, onDownload }
}

describe('the CA list on a phone', () => {
  it('draws one record per authority with the facts of its row', () => {
    const cas = [...smallHierarchy().slice(0, 2), ca(7, { name: 'Edge', type: 'intermediate', parent_id: 1, key_algorithm: 'ECDSA P-256' })]
    renderList(cas)
    expect(screen.queryByRole('table')).toBeNull()
    const services = record('Services')
    const meta = [...services.querySelectorAll('.lv-mrecord-meta > span')].map((s) => s.textContent)
    expect(meta.slice(0, 3)).toEqual(['common.intermediateCA', 'Example Root', 'cas.certificateCount:{"count":12}'])
    expect(record('Edge').querySelector('.lv-mrecord-meta')).toHaveTextContent('ECDSA P-256')
    // state and expiry, as the Status and Expires columns
    expect(services.querySelector('.lv-mrecord-status .lv-pill')).toHaveTextContent('common.active')
    expect(services.querySelector('.lv-mrecord-end').textContent).not.toBe('')
  })

  it('keeps the marks of the row (offline here), named for assistive technology', () => {
    renderList()
    expect(within(record('Second Root')).getByRole('img', { name: 'cas.offline' })).toBeInTheDocument()
  })

  it('opens the detail from the record and from its chevron', () => {
    const { onSelect } = renderList()
    fireEvent.click(record('Services').querySelector('.lv-mrecord-meta'))
    expect(onSelect).toHaveBeenCalledTimes(1)
    expect(onSelect.mock.calls[0][0]).toMatchObject({ id: 2 })
    const chevron = within(record('Legacy')).getByRole('button', { name: 'table.openRow:{"name":"Legacy"}' })
    fireEvent.click(chevron)
    expect(onSelect).toHaveBeenCalledTimes(2)
    expect(onSelect.mock.calls[1][0]).toMatchObject({ id: 4 })
  })

  it('keeps its table, chevron and download on a wider screen', () => {
    screenSize.isMobile = false
    const { onDownload } = renderList()
    expect(screen.getByRole('table')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'table.rowAction:{"action":"cas.downloadCertificate","name":"Services"}' }))
    expect(onDownload).toHaveBeenCalledWith(expect.objectContaining({ id: 2 }))
  })
})
