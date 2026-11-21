/**
 * Encryption at rest in the mockup's dialog: turning it on waits for the three acknowledgements
 * and the typed word, and the master key shown once after cannot be closed before it is
 * downloaded and its storage confirmed.
 */
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (key, vars) => (vars?.word ? `${key}:${vars.word}` : key) }),
}))

import { EnableEncryptionDialog, MasterKeyBackupDialog } from '../EncryptionDialogs'

describe('turning encryption on', () => {
  const setup = (props = {}) => {
    const onConfirm = vi.fn()
    const onClose = vi.fn()
    render(<EnableEncryptionDialog open onConfirm={onConfirm} onClose={onClose} {...props} />)
    return { onConfirm, onClose, submit: () => screen.getByRole('button', { name: 'settings.enableEncryption' }) }
  }

  it('is drawn as the mockup dialog, warning first', () => {
    setup()
    const dialog = screen.getByRole('dialog')
    expect(dialog.closest('.atl')).not.toBeNull()
    expect(dialog.querySelector('.notice.warn')).toHaveTextContent('settings.encryptionWarningTitle')
    expect(screen.getAllByRole('checkbox')).toHaveLength(3)
    for (const box of screen.getAllByRole('checkbox')) expect(box.closest('label')).toHaveClass('checkbox-line')
  })

  it('waits for the three acknowledgements and the typed word', () => {
    const { onConfirm, submit } = setup()
    expect(submit()).toBeDisabled()
    for (const name of ['settings.encryptionCheckKeyFile', 'settings.encryptionCheckBackup', 'settings.encryptionCheckLostKeys']) {
      fireEvent.click(screen.getByRole('checkbox', { name }))
    }
    expect(submit()).toBeDisabled()
    fireEvent.change(screen.getByLabelText('settings.typeToConfirm:ENCRYPT'), { target: { value: 'encrypt' } })
    expect(submit()).toBeDisabled()
    fireEvent.change(screen.getByLabelText('settings.typeToConfirm:ENCRYPT'), { target: { value: 'ENCRYPT' } })
    expect(submit()).toBeEnabled()
    fireEvent.click(submit())
    expect(onConfirm).toHaveBeenCalledTimes(1)
  })

  it('starts over when opened again', () => {
    const { rerender } = render(<EnableEncryptionDialog open onConfirm={vi.fn()} onClose={vi.fn()} />)
    fireEvent.click(screen.getByRole('checkbox', { name: 'settings.encryptionCheckKeyFile' }))
    rerender(<EnableEncryptionDialog open={false} onConfirm={vi.fn()} onClose={vi.fn()} />)
    rerender(<EnableEncryptionDialog open onConfirm={vi.fn()} onClose={vi.fn()} />)
    expect(screen.getByRole('checkbox', { name: 'settings.encryptionCheckKeyFile' })).not.toBeChecked()
  })

  it('keeps its buttons still while the request runs', () => {
    const { onClose } = setup({ loading: true })
    expect(screen.getByRole('button', { name: 'common.cancel' })).toBeDisabled()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(onClose).not.toHaveBeenCalled()
  })
})

describe('the master key shown once', () => {
  const setup = (props = {}) => {
    const onDownload = vi.fn()
    const onDone = vi.fn()
    const view = render(<MasterKeyBackupDialog open downloaded={false} onDownload={onDownload} onDone={onDone} {...props} />)
    return { onDownload, onDone, view }
  }

  it('cannot be closed before the key is downloaded and its storage confirmed', () => {
    const { onDone, onDownload, view } = setup()
    const done = screen.getByRole('button', { name: 'common.done' })
    expect(done).toBeDisabled()
    expect(screen.getByRole('checkbox', { name: 'settings.masterKeyBackupConfirm' })).toBeDisabled()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    fireEvent.click(screen.getByRole('button', { name: 'common.closeWindow' }))
    expect(onDone).not.toHaveBeenCalled()
    fireEvent.click(screen.getByRole('button', { name: 'settings.masterKeyDownloadNow' }))
    expect(onDownload).toHaveBeenCalledTimes(1)
    view.rerender(<MasterKeyBackupDialog open downloaded onDownload={onDownload} onDone={onDone} />)
    expect(screen.getByRole('button', { name: 'settings.masterKeyDownloadAgain' })).toBeInTheDocument()
    expect(done).toBeDisabled()
    fireEvent.click(screen.getByRole('checkbox', { name: 'settings.masterKeyBackupConfirm' }))
    expect(done).toBeEnabled()
    fireEvent.keyDown(screen.getByRole('dialog'), { key: 'Escape' })
    expect(onDone).toHaveBeenCalledTimes(1)
    fireEvent.click(done)
    expect(onDone).toHaveBeenCalledTimes(2)
  })
})
