/**
 * Sectioned form template: table of contents by groups with its marks, the jump select,
 * a frame per section that names its save error and survives a crashing body, and the
 * save bar in its three states (nothing pending, pending, failed).
 */
import { describe, it, expect, vi } from 'vitest'
import { fireEvent, render, screen, within } from '@testing-library/react'
import { Gear, Envelope } from '@phosphor-icons/react'

vi.mock('react-i18next', () => {
  const t = (key, opts) => (opts ? `${key}:${JSON.stringify(opts)}` : key)
  return { useTranslation: () => ({ t, i18n: { language: 'en' } }) }
})

import { SectionToc, SectionJump, FormSection, FormGroup, SaveBar, sectionDomId } from '..'

const SECTIONS = [
  { id: 'general', label: 'General', icon: Gear },
  { id: 'email', label: 'Email', icon: Envelope },
  { id: 'about', label: 'About' },
]
const GROUPS = [
  { id: 'system', label: 'System', ids: ['general'] },
  { id: 'notify', label: 'Notifications', ids: ['email', 'missing'] },
  { id: 'empty', label: 'Empty', ids: ['nothing'] },
  { id: 'info', label: 'Info', ids: ['about'] },
]

describe('SectionToc', () => {
  it('lists the sections by group, a group without section left out', () => {
    render(<SectionToc label="Sections" sections={SECTIONS} groups={GROUPS} onJump={vi.fn()} />)
    const nav = screen.getByRole('navigation', { name: 'Sections' })
    const groups = within(nav).getAllByRole('group')
    expect(groups.map((g) => within(g).getAllByRole('link').map((a) => a.textContent)))
      .toEqual([['General'], ['Email'], ['About']])
    expect(groups[1]).toHaveAccessibleName('Notifications')
    expect(within(nav).queryByText('Empty')).toBeNull()
  })

  it('jumps on a plain click and leaves a modified click to the browser', () => {
    const onJump = vi.fn()
    render(<SectionToc label="Sections" sections={SECTIONS} hrefFor={(id) => `/settings?tab=${id}`} onJump={onJump} />)
    const link = screen.getByRole('link', { name: 'Email' })
    expect(link).toHaveAttribute('href', '/settings?tab=email')
    expect(fireEvent.click(link)).toBe(false)
    expect(onJump).toHaveBeenCalledWith('email')
    onJump.mockClear()
    expect(fireEvent.click(link, { ctrlKey: true })).toBe(true)
    expect(onJump).not.toHaveBeenCalled()
  })

  it('marks a modified section and one to correct, in words', () => {
    render(<SectionToc label="Sections" sections={SECTIONS} flags={{ general: 'modified', email: 'error' }} onJump={vi.fn()} />)
    expect(screen.getByRole('link', { name: /General/ })).toHaveTextContent('sectioned.flagModified')
    expect(screen.getByRole('link', { name: /Email/ })).toHaveTextContent('sectioned.flagError')
    expect(screen.getByRole('link', { name: 'About' })).not.toHaveTextContent('sectioned')
  })

  it('marks the shown section as current', () => {
    render(<SectionToc label="Sections" sections={SECTIONS} current="email" onJump={vi.fn()} />)
    expect(screen.getByRole('link', { name: 'Email' })).toHaveAttribute('aria-current', 'true')
    expect(screen.getByRole('link', { name: 'General' })).not.toHaveAttribute('aria-current')
  })
})

describe('SectionJump', () => {
  it('offers every section and jumps to the one chosen', () => {
    const onJump = vi.fn()
    render(<SectionJump label="Go to section" sections={SECTIONS} value="general" onJump={onJump} />)
    const select = screen.getByLabelText('Go to section')
    expect([...select.options].map((o) => o.value)).toEqual(['general', 'email', 'about'])
    fireEvent.change(select, { target: { value: 'about' } })
    expect(onJump).toHaveBeenCalledWith('about')
  })
})

describe('FormSection', () => {
  it('is a region named by its title, with its sentence and an anchor id', () => {
    render(<FormSection id="email" title="Email" description="SMTP relay.">body</FormSection>)
    const region = screen.getByRole('region', { name: 'Email' })
    expect(region).toHaveAttribute('id', sectionDomId('email'))
    expect(region).toHaveTextContent('SMTP relay.')
    expect(screen.getByRole('heading', { name: 'Email', level: 2 })).toHaveAttribute('tabindex', '-1')
  })

  it('names the error of its save', () => {
    render(<FormSection id="email" title="Email" error="SMTP refused">body</FormSection>)
    expect(screen.getByRole('alert')).toHaveTextContent('SMTP refused')
    expect(screen.getByRole('region', { name: 'Email' })).toHaveClass('is-error')
  })

  it('keeps its frame when its body fails to render', () => {
    const Broken = () => { throw new Error('boom') }
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    render(
      <>
        <FormSection id="a" title="A"><Broken /></FormSection>
        <FormSection id="b" title="B">still here</FormSection>
      </>,
    )
    spy.mockRestore()
    expect(screen.getByRole('region', { name: 'A' })).toHaveTextContent('sectioned.sectionFailed')
    expect(screen.getByText('still here')).toBeInTheDocument()
  })
})

describe('FormGroup', () => {
  it('gives its fields a legend, a description and actions', () => {
    render(<FormGroup title="SMTP" description="Relay" actions={<button type="button">Refresh</button>}>fields</FormGroup>)
    const group = screen.getByRole('region', { name: 'SMTP' })
    expect(group).toHaveTextContent('Relay')
    expect(within(group).getByRole('button', { name: 'Refresh' })).toBeInTheDocument()
  })
})

describe('SaveBar', () => {
  it('says nothing is pending, with the last save, its buttons off', () => {
    render(<SaveBar count={0} lastSaved={{ at: '6 Nov 2026, 10:12', by: 'admin' }} onReset={vi.fn()} onSave={vi.fn()} />)
    expect(screen.getByText(/sectioned\.nothingPending/)).toHaveTextContent('sectioned.lastSavedBy')
    expect(screen.getByRole('button', { name: 'sectioned.undo' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'common.save' })).toBeDisabled()
  })

  it('without a known last save says only that nothing is pending', () => {
    render(<SaveBar count={0} onReset={vi.fn()} onSave={vi.fn()} />)
    expect(screen.getByTestId('sf-savebar')).not.toHaveTextContent('lastSaved')
  })

  it('counts the changes and names their sections; undo and save act', () => {
    const onReset = vi.fn()
    const onSave = vi.fn()
    render(<SaveBar count={3} sectionLabels={['General', 'Email']} onReset={onReset} onSave={onSave} />)
    const bar = screen.getByTestId('sf-savebar')
    expect(bar).toHaveClass('is-dirty')
    expect(bar).toHaveTextContent('sectioned.pendingTitle')
    expect(bar).toHaveTextContent('"count":3')
    expect(bar).toHaveTextContent('"sections":"General, Email"')
    fireEvent.click(screen.getByRole('button', { name: 'sectioned.undo' }))
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    expect(onReset).toHaveBeenCalledTimes(1)
    expect(onSave).toHaveBeenCalledTimes(1)
  })

  it('names the changed fields when their labels are known, as the mockup does', () => {
    render(<SaveBar count={2} sectionLabels={['General']} fieldLabels={['Instance name', 'Port']} onReset={vi.fn()} onSave={vi.fn()} />)
    const bar = screen.getByTestId('sf-savebar')
    expect(bar).toHaveTextContent('sectioned.pendingTitle')
    expect(bar).toHaveTextContent('sectioned.pendingFields')
    expect(bar).toHaveTextContent('"fields":"Instance name, Port"')
    expect(bar).not.toHaveTextContent('"count":2')
  })

  it('names the sections whose save failed, buttons still there', () => {
    render(<SaveBar count={1} sectionLabels={['Email']} failed={['Email']} onReset={vi.fn()} onSave={vi.fn()} />)
    const bar = screen.getByTestId('sf-savebar')
    expect(bar).toHaveClass('is-error')
    expect(bar).toHaveTextContent('sectioned.saveFailedTitle')
    expect(screen.getByRole('button', { name: 'common.save' })).toBeEnabled()
  })

  it('holds both buttons while saving', () => {
    render(<SaveBar count={2} saving onReset={vi.fn()} onSave={vi.fn()} />)
    expect(screen.getByRole('button', { name: 'sectioned.undo' })).toBeDisabled()
    expect(screen.getByRole('button', { name: 'sectioned.saving' })).toBeDisabled()
  })
})
