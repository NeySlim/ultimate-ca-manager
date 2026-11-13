/** The keytab upload needs write:kerberos as well as write:xcep: the section passes that down. */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

const mocks = vi.hoisted(() => ({ editorProps: null }))

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key, i18n: { language: 'en' } }),
  initReactI18next: { type: '3rdParty', init: vi.fn() },
}))
vi.mock('../../../services', () => ({ casService: { getAll: () => Promise.resolve({ data: [] }) } }))
vi.mock('../../../components', () => ({
  DetailHeader: () => null,
  DetailSection: ({ children }) => <div>{children}</div>,
  DetailContent: ({ children }) => <div>{children}</div>,
  Modal: ({ open, children }) => (open ? <div>{children}</div> : null),
}))
vi.mock('../WindowsSettingsPanel', () => ({ default: () => null }))
vi.mock('../WindowsProfileList', () => ({
  default: ({ onEdit }) => <button type="button" onClick={() => onEdit({ id: 7, name: 'corp' })}>edit</button>,
}))
vi.mock('../WindowsProfileEditor', () => ({
  default: (props) => { mocks.editorProps = props; return null },
}))

import XcepWstepSection from '../XcepWstepSection'

const open = (granted) => {
  mocks.editorProps = null
  render(<XcepWstepSection hasPermission={(p) => granted.includes(p)} />)
  fireEvent.click(screen.getByText('edit'))
  return mocks.editorProps
}

describe('keytab permission', () => {
  it('withholds the keytab upload from write:xcep alone', () => {
    const props = open(['write:xcep'])
    expect(props.canWrite).toBe(true)
    expect(props.canUploadKeytab).toBe(false)
  })

  it('grants it with write:xcep and write:kerberos', () => {
    expect(open(['write:xcep', 'write:kerberos']).canUploadKeytab).toBe(true)
  })

  it('withholds it from write:kerberos alone', () => {
    expect(open(['write:kerberos']).canUploadKeytab).toBe(false)
  })
})
