/**
 * Initial focus of a dialog, as the mockup: the first field of the body, or the element marked
 * data-autofocus (the safe action of a confirmation); with neither, the close button.
 */
import { describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => k }) }))

import { ListDialog } from '../ListDialog'

const open = (children) => render(<ListDialog open onOpenChange={() => {}} title="Dialog">{children}</ListDialog>)

describe('ListDialog initial focus', () => {
  it('goes to the first field of the body', async () => {
    open(<form><p>Lead</p><button type="button">Help</button><label>Name<input /></label><label>Mail<input /></label></form>)
    expect(await screen.findByRole('textbox', { name: 'Name' })).toHaveFocus()
  })

  it('skips a hidden, disabled or read-only field', async () => {
    open(<form>
      <input type="hidden" name="csrf" />
      <input type="file" className="hidden" aria-label="File" />
      <label>Fixed<input readOnly defaultValue="x" /></label>
      <label>Off<input disabled /></label>
      <label>Kind<select><option>One</option></select></label>
    </form>)
    expect(await screen.findByRole('combobox', { name: 'Kind' })).toHaveFocus()
  })

  it('goes to the element marked data-autofocus before any field', async () => {
    open(<><label>Reason<input /></label><button type="button" data-autofocus>Cancel</button></>)
    expect(await screen.findByRole('button', { name: 'Cancel' })).toHaveFocus()
  })

  it('keeps the close button over a list of check boxes, as the mockup\'s Columns dialog', async () => {
    open(<><label><input type="checkbox" />Name</label><label><input type="checkbox" />State</label></>)
    expect(await screen.findByRole('button', { name: 'common.closeWindow' })).toHaveFocus()
  })

  it('keeps the close button when the body has nothing to fill', async () => {
    open(<p>Three nodes are up to date.</p>)
    expect(await screen.findByRole('button', { name: 'common.closeWindow' })).toHaveFocus()
  })
})
