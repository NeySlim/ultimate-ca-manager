import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key) => key }),
}))

vi.mock('../../../components', () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label }) => <label>{label}</label>,
  Select: () => <select />,
  FileUpload: () => <div />,
  Badge: ({ children }) => <span>{children}</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))

vi.mock('../../../components/ui/ToggleSwitch', () => ({
  ToggleSwitch: ({ label }) => <span>{label}</span>,
}))

import BackupSection from '../BackupSection'

const archive = { filename: 'ucm_backup_1.ucmbkp', size: '1.0 MB', created_at: '2026-11-14 10:00:00 UTC' }

const renderSection = (backupMeta, backups) => render(
  <BackupSection
    settings={{}}
    updateSetting={vi.fn()}
    handleSave={vi.fn()}
    saving={false}
    hasPermission={() => true}
    backups={backups}
    backupMeta={backupMeta}
  />
)

describe('BackupSection in high availability', () => {
  it('names the node of each archive and says the database is not a recovery of itself', () => {
    renderSection({ storage: 'database', total: 1 }, [{ ...archive, node: 'node-a', sha256: 'ab'.repeat(32) }])
    expect(screen.getByText('settings.backupSharedStoreNote')).toBeTruthy()
    expect(screen.getByText(/node-a/)).toBeTruthy()
    expect(screen.getByTitle('ab'.repeat(32))).toBeTruthy()
  })

  it('says nothing of nodes for archives on disk', () => {
    renderSection({ storage: 'disk', total: 1 }, [archive])
    expect(screen.queryByText('settings.backupSharedStoreNote')).toBeNull()
    expect(screen.queryByText(/settings.backupNode/)).toBeNull()
  })
})
