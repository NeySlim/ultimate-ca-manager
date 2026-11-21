import { describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, vars) => (vars ? `${key} ${JSON.stringify(vars)}` : key) }),
}))
vi.mock('../../../hooks/useClipboard', () => ({
  useClipboard: () => ({ copy: vi.fn(), isCopied: () => false }),
}))
vi.mock('../../../components/ui/ToggleSwitch', () => ({
  ToggleSwitch: ({ label }) => <span>{label}</span>,
}))

vi.mock('../../../components', async () => ({
  Button: ({ children, ...props }) => <button {...props}>{children}</button>,
  Input: ({ label }) => <label>{label}</label>,
  Select: () => <select />,
  FileUpload: (await import('../../../components/FileUpload')).FileUpload,
  Badge: ({ children }) => <span>{children}</span>,
  DetailHeader: ({ title }) => <header>{title}</header>,
  DetailSection: ({ title, children }) => <section><h2>{title}</h2>{children}</section>,
  DetailContent: ({ children }) => <div>{children}</div>,
}))

// The real FileUpload and its siblings: the point is what the picker does with a file.
import BackupSection from '../BackupSection'
import { FileUpload } from '../../../components/FileUpload'

const MIB = 1024 * 1024
const fakeFile = (mib) => {
  const file = new File(['x'], 'big.ucmbkp')
  Object.defineProperty(file, 'size', { value: mib * MIB })
  return file
}
const pick = (container, file) =>
  fireEvent.change(container.querySelector('input[type=file]'), { target: { files: [file] } })

const setup = (restore_limits, setRestoreFile = vi.fn()) => {
  const view = render(
    <BackupSection settings={{}} updateSetting={vi.fn()} handleSave={vi.fn()} saving={false}
      hasPermission={() => true} backups={[]} backupMeta={{ total: 0, restore_limits }}
      setRestoreFile={setRestoreFile} setShowRestoreModal={vi.fn()} />
  )
  return { ...view, setRestoreFile }
}

describe('restore picker follows the server ceilings', () => {
  it('lets an 11 MiB archive through', async () => {
    const { container, setRestoreFile } = setup({ upload_bytes: 512 * MIB, archive_bytes: 0 })
    const file = fakeFile(11)
    pick(container, file)
    await waitFor(() => expect(setRestoreFile).toHaveBeenCalledWith(file))
  })

  it('sets no client ceiling when v4 archives have none (archive_bytes 0)', async () => {
    const { container, setRestoreFile } = setup({ upload_bytes: 512 * MIB, archive_bytes: 0 })
    const file = fakeFile(1024)
    pick(container, file)
    await waitFor(() => expect(setRestoreFile).toHaveBeenCalledWith(file))
  })

  it('refuses a file above the announced ceiling and says it', () => {
    const { container, setRestoreFile } = setup({ upload_bytes: 512 * MIB, archive_bytes: 2048 * MIB })
    pick(container, fakeFile(3000))
    expect(setRestoreFile).not.toHaveBeenCalled()
    expect(screen.getByText(/2\.0GB/)).toBeTruthy()
  })

  it('takes the larger of the two ceilings', async () => {
    const { container, setRestoreFile } = setup({ upload_bytes: 512 * MIB, archive_bytes: 100 * MIB })
    pick(container, fakeFile(400))
    await waitFor(() => expect(setRestoreFile).toHaveBeenCalled())
  })
})

// The server reads the format from the first bytes: "UCMB" then the version byte.
const archive = (mib, head) => {
  const file = new File([head], 'big.ucmbkp')
  Object.defineProperty(file, 'size', { value: mib * MIB })
  return file
}
const V3 = 'UCMB\x03\x00\x01\x00\x00\x00'
const V4 = 'UCMB\x04\x00\x02\x00\x00\x00'

describe('restore picker applies the ceiling of the archive format', () => {
  const limits = { upload_bytes: 512 * MIB, archive_bytes: 0 }

  it('refuses an archive written before 3.0 above BACKUP_MAX_UPLOAD_MB, naming the ceiling', async () => {
    const { container, setRestoreFile } = setup(limits)
    pick(container, archive(600, V3))
    await waitFor(() => expect(screen.getByText(/settings\.restoreTooLargeLegacy/)).toBeTruthy())
    expect(screen.getByText(/512MB/)).toBeTruthy()
    expect(setRestoreFile).not.toHaveBeenCalled()
  })

  it('accepts a v4 archive of the same size', async () => {
    const { container, setRestoreFile } = setup(limits)
    const file = archive(600, V4)
    pick(container, file)
    await waitFor(() => expect(setRestoreFile).toHaveBeenCalledWith(file))
  })

  it('leaves a file whose header it does not know to the server', async () => {
    const { container, setRestoreFile } = setup(limits)
    const file = archive(600, 'not an archive')
    pick(container, file)
    await waitFor(() => expect(setRestoreFile).toHaveBeenCalledWith(file))
  })

  it('accepts an older archive under the ceiling', async () => {
    const { container, setRestoreFile } = setup(limits)
    const file = archive(100, V3)
    pick(container, file)
    await waitFor(() => expect(setRestoreFile).toHaveBeenCalledWith(file))
  })
})

describe('other uploads keep the 10 MiB default', () => {
  it('refuses 11 MiB', () => {
    const onFileSelect = vi.fn()
    const { container } = render(<FileUpload onFileSelect={onFileSelect} />)
    pick(container, fakeFile(11))
    expect(onFileSelect).not.toHaveBeenCalled()
    expect(screen.getByText('File size exceeds 10MB')).toBeTruthy()
  })
})
