/**
 * The configuration form of the Atelier mockup (settingsView): every change goes to the page, the
 * table of contents marks what changed and what to correct, the save bar says what is pending, a
 * section's test shows its result, the jump select and the links reach a section's title.
 */
import { useState } from 'react'
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, within } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k), i18n: { language: 'fr' } }),
}))

import { SettingsView } from '../SettingsView'

const sections = [
  { id: 'general', label: 'Général', icon: 'settings', desc: 'Identité.', groups: [{ legend: 'Instance', fields: [
    { key: 'instance', label: 'Nom de l’instance', hint: 'Affiché.' },
    { key: 'timezone', label: 'Fuseau', short: true, options: [['UTC', 'UTC'], ['Europe/Paris', 'Paris']] },
  ] }] },
  { id: 'smtp', label: 'SMTP', icon: 'send', desc: 'Relais.', groups: [{ legend: 'Relais', fields: [
    { key: 'smtpPort', label: 'Port', short: true, numeric: true },
    { key: 'notify', label: 'Notifier', checkbox: true },
    { key: 'fips', label: 'FIPS', readonly: 'Désactivé', hint: 'Lecture seule.' },
  ] }] },
]
const saved = { instance: 'UCM', timezone: 'UTC', smtpPort: '587', notify: true }

function Page({ errors = {}, onSave = () => {}, test, failed, onJump }) {
  const [values, setValues] = useState(saved)
  const changed = Object.keys(saved).filter((k) => String(values[k]) !== String(saved[k]))
  const s = test ? sections.map((x) => (x.id === 'smtp' ? { ...x, test } : x)) : sections
  return <SettingsView sections={s} values={values} errors={errors} changed={changed} failed={failed} tocLabel="Sections"
    onChange={(k, v) => setValues((p) => ({ ...p, [k]: v }))} onReset={() => setValues(saved)} onSave={onSave} lastSaved={{ at: '6 nov.', by: 'admin' }} onJump={onJump} />
}

describe('the configuration form', () => {
  it('says nothing is pending, with the last save, and holds its buttons', () => {
    render(<Page />)
    expect(document.getElementById('settings-state')).toHaveTextContent('sectioned.nothingPending sectioned.lastSavedBy {"date":"6 nov.","user":"admin"}')
    expect(screen.getByRole('button', { name: 'sectioned.undo' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'common.save' })).toBeDisabled()
  })
  it('marks a changed field in the state, its section in the contents, and undoes it', () => {
    const { container } = render(<Page />)
    fireEvent.change(screen.getByLabelText('Port'), { target: { value: '465' } })
    fireEvent.click(screen.getByLabelText('Notifier'))
    expect(document.getElementById('settings-state')).toHaveTextContent('sectioned.pendingFields {"fields":"Port, Notifier"}')
    expect(container.querySelector('#settings-savebar')).toHaveClass('dirty')
    const toc = screen.getByRole('navigation', { name: 'Sections' })
    expect(within(toc).getByRole('link', { name: /SMTP/ })).toHaveTextContent('sectioned.flagModified')
    expect(within(toc).getByRole('link', { name: /Général/ })).not.toHaveTextContent('sectioned.flagModified')
    fireEvent.click(screen.getByRole('button', { name: 'sectioned.undo' }))
    expect(screen.getByLabelText('Port')).toHaveValue('587')
    expect(container.querySelector('#settings-savebar')).not.toHaveClass('dirty')
  })
  it('saves by the form, Enter in a field included', () => {
    const onSave = vi.fn()
    render(<Page onSave={onSave} />)
    fireEvent.change(screen.getByLabelText('Nom de l’instance'), { target: { value: 'UCM 2' } })
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    fireEvent.submit(screen.getByLabelText('Nom de l’instance').closest('form'))
    expect(onSave).toHaveBeenCalledTimes(2)
  })
  it('shows an error under its field, names it, and marks its section to correct', () => {
    render(<Page errors={{ smtpPort: 'Port hors plage.' }} />)
    const port = screen.getByLabelText('Port')
    expect(port).toHaveAttribute('aria-invalid', 'true')
    expect(port).toHaveAttribute('aria-describedby', 'err-set-smtpPort')
    expect(document.getElementById('err-set-smtpPort')).toHaveTextContent('Port hors plage.')
    expect(screen.getByRole('link', { name: /SMTP/ })).toHaveTextContent('sectioned.flagError')
    expect(screen.getByLabelText('Nom de l’instance')).toHaveAttribute('aria-describedby', 'hint-set-instance')
  })
  it('draws a select, a checkbox line, a read-only value', () => {
    render(<Page />)
    expect(screen.getByLabelText('Fuseau').tagName).toBe('SELECT')
    expect(screen.getByLabelText('Fuseau').closest('.field')).toHaveClass('short')
    expect(screen.getByLabelText('Notifier').closest('label')).toHaveClass('checkbox-line', 'field', 'full')
    // A read-only value is a chip to copy, named by its label, not a greyed field
    const fips = screen.getByRole('group', { name: 'FIPS' })
    expect(fips.querySelector('input')).toBeNull()
    expect(fips.querySelector('.code-value')).toHaveTextContent('Désactivé')
    expect(within(fips).getByRole('button', { name: 'protocols.copyValue {"name":"FIPS"}' })).toBeTruthy()
    expect(fips).toHaveAttribute('aria-describedby', 'hint-set-fips')
  })
  it('runs a section test and shows its result, or the hint before', () => {
    const onTest = vi.fn()
    const { rerender } = render(<Page test={{ label: 'Tester SMTP', hint: 'Test simulé.', onTest, result: null }} />)
    expect(document.getElementById('test-result-smtp')).toHaveTextContent('Test simulé.')
    fireEvent.click(screen.getByRole('button', { name: 'Tester SMTP' }))
    expect(onTest).toHaveBeenCalled()
    rerender(<Page test={{ label: 'Tester SMTP', hint: 'x', onTest, result: { ok: false, text: 'Échec.' } }} />)
    expect(document.getElementById('test-result-smtp')).toHaveClass('test-result', 'bad')
  })
  it('jumps to a section from the select and the contents, its title focused, and tells the page', () => {
    const onJump = vi.fn()
    render(<Page onJump={onJump} />)
    const title = document.getElementById('set-title-smtp')
    fireEvent.change(screen.getByLabelText('sectioned.jumpLabel'), { target: { value: 'smtp' } })
    expect(document.activeElement).toBe(title)
    document.body.focus()
    fireEvent.click(screen.getByRole('link', { name: /SMTP/ }))
    expect(document.activeElement).toBe(title)
    expect(onJump.mock.calls).toEqual([['smtp'], ['smtp']])
  })
  it('says which sections failed to save', () => {
    render(<Page failed={['SMTP']} />)
    expect(document.getElementById('settings-state')).toHaveTextContent('sectioned.saveFailedIn {"sections":"SMTP"}')
  })
})
