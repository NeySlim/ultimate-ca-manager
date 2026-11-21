/**
 * The mockup's form fields and dialogs, with the props of the product components they replace:
 * a label that names its control, the hint and the error named by aria-describedby, the field's
 * place in its grid, a select that hands back the value, a check line, a radio choice, and the
 * form dialog that submits once, its named values in hand.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent, waitFor } from '@testing-library/react'
import { Input, Select, Textarea, ToggleSwitch, ChoiceField, FormModal, Modal, ConfirmModal } from '../Form'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k }) }))

describe('fields', () => {
  it('draws an input as the mockup field: label, hint, error, place', () => {
    const { container } = render(<Input label="Nom" helperText="Affiché partout" error="Requis" short value="" onChange={() => {}} />)
    const box = screen.getByLabelText('Nom')
    const field = container.querySelector('.field')
    expect(field).toHaveClass('short')
    expect(box).toHaveAttribute('aria-invalid', 'true')
    const ids = box.getAttribute('aria-describedby').split(' ')
    expect(ids.map((id) => document.getElementById(id).textContent)).toEqual(['Affiché partout', 'Requis'])
    expect(field.querySelector('.field-error')).toHaveTextContent('Requis')
  })

  it('masks a stored secret and says typing replaces it', () => {
    render(<Input label="Mot de passe" type="password" hasExistingValue required value="" onChange={() => {}} />)
    const box = screen.getByLabelText('Mot de passe')
    expect(box).toHaveAttribute('placeholder', '••••••••••••')
    expect(box).not.toBeRequired()
    expect(screen.getByText('common.enterNewToChange')).toBeInTheDocument()
  })

  it('hands back the chosen value of a native select, a placeholder first', () => {
    const onChange = vi.fn()
    render(<Select label="Type" value="" placeholder="Choisir" onChange={onChange} options={[{ value: 'a', label: 'A' }, { value: 'b', label: 'B' }]} full />)
    const select = screen.getByLabelText('Type')
    expect([...select.options].map((o) => o.textContent)).toEqual(['Choisir', 'A', 'B'])
    fireEvent.change(select, { target: { value: 'b' } })
    expect(onChange).toHaveBeenCalledWith('b')
    expect(select.closest('.field')).toHaveClass('full')
  })

  it('sets a textarea full width, in monospace when asked', () => {
    render(<Textarea label="Clé" mono value="" onChange={() => {}} />)
    const area = screen.getByLabelText('Clé')
    expect(area).toHaveClass('mono')
    expect(area.closest('.field')).toHaveClass('full')
  })

  it('draws a toggle as a check line, its description as the hint', () => {
    const onChange = vi.fn()
    const { container } = render(<ToggleSwitch label="Activer" description="Envoie aussi" checked={false} onChange={onChange} />)
    const box = screen.getByRole('checkbox', { name: 'Activer' })
    expect(container.querySelector('label.checkbox-line')).toContainElement(box)
    expect(document.getElementById(box.getAttribute('aria-describedby'))).toHaveTextContent('Envoie aussi')
    fireEvent.click(box)
    expect(onChange).toHaveBeenCalledWith(true)
  })

  it('offers a choice as format options in a choice grid', () => {
    const onChange = vi.fn()
    const { container } = render(<ChoiceField name="src" legend="Origine" value="a" onChange={onChange}
      options={[{ value: 'a', label: 'Logiciel' }, { value: 'b', label: 'HSM', hint: 'Clé existante' }]} />)
    expect(container.querySelectorAll('.choice-grid > label.format-option')).toHaveLength(2)
    fireEvent.click(screen.getByRole('radio', { name: /HSM/ }))
    expect(onChange).toHaveBeenCalledWith('b')
  })
})

describe('dialogs', () => {
  it('submits the named values once, Annuler and the primary under the rule', async () => {
    let finish
    const onSubmit = vi.fn(() => new Promise((r) => { finish = r }))
    render(
      <FormModal open title="Créer" onClose={() => {}} onSubmit={onSubmit} submitLabel="Créer">
        <Input label="Nom" name="name" defaultValue="ca-1" />
      </FormModal>,
    )
    const dialog = document.querySelector('dialog')
    expect(dialog).toHaveAttribute('aria-labelledby', 'modal-title')
    const actions = dialog.querySelector('.modal-actions')
    expect([...actions.children].map((b) => b.className)).toEqual(['btn', 'btn primary'])
    const submit = screen.getByRole('button', { name: 'Créer' })
    fireEvent.click(submit)
    fireEvent.click(submit)
    await waitFor(() => expect(onSubmit).toHaveBeenCalledTimes(1))
    expect(onSubmit).toHaveBeenCalledWith({ name: 'ca-1' })
    finish()
  })

  it('mounts a modal only while it is open, closed by its close button', () => {
    const onClose = vi.fn()
    const { rerender } = render(<Modal open={false} title="Importer" onClose={onClose}>corps</Modal>)
    expect(document.querySelector('dialog')).toBeNull()
    rerender(<Modal open title="Importer" size="lg" onClose={onClose}>corps</Modal>)
    expect(document.querySelector('dialog')).toHaveClass('wide')
    fireEvent.click(screen.getByRole('button', { name: 'common.closeWindow' }))
    expect(onClose).toHaveBeenCalled()
  })

  it('confirms with a danger button', () => {
    const onConfirm = vi.fn()
    render(<ConfirmModal open message="Supprimer ?" confirmLabel="Supprimer" onConfirm={onConfirm} onClose={() => {}} />)
    const btn = screen.getByRole('button', { name: 'Supprimer' })
    expect(btn).toHaveClass('btn', 'danger')
    fireEvent.click(btn)
    expect(onConfirm).toHaveBeenCalled()
  })
})
