/**
 * The pieces a settings page composes (settingsView() split): a column that is not a form when the
 * sections hold their own, a frame drawn under the mockup rules, a
 * group with its sentence, a test with its outcome announced, a save bar outside any form, a table
 * of contents that links to a page address, and the quiet focus of a link landing.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, fireEvent } from '@testing-library/react'

vi.mock('react-i18next', () => ({
  useTranslation: () => ({ t: (k, p) => (p ? `${k} ${JSON.stringify(p)}` : k) }),
}))

import { SettingsLayout, SettingsFrame, SettingsGroup, SettingsTest, SettingsSaveBar, SettingsToc, SettingsJump } from '../SettingsView'
import { jumpTo } from '../helpers'

describe('settings layout', () => {
  it('holds the sections in a div when they bring forms of their own, a form otherwise', () => {
    const { rerender } = render(<SettingsLayout toc={<nav />}><form data-testid="own"><input aria-label="x" /></form></SettingsLayout>)
    expect(document.getElementById('settings-form').tagName).toBe('DIV')
    expect(screen.getByTestId('own').parentElement).toBe(document.getElementById('settings-form'))
    const onSubmit = vi.fn()
    rerender(<SettingsLayout toc={<nav />} onSubmit={onSubmit}><input aria-label="y" /></SettingsLayout>)
    expect(document.getElementById('settings-form').tagName).toBe('FORM')
    fireEvent.submit(document.getElementById('settings-form'))
    expect(onSubmit).toHaveBeenCalledTimes(1)
  })

  it('puts the history after the column, inside the main part', () => {
    render(<SettingsLayout toc={<nav />} history={<section data-testid="history" />}><p>x</p></SettingsLayout>)
    const main = document.querySelector('.settings-main')
    expect(main.lastElementChild).toBe(screen.getByTestId('history'))
    expect(main.firstElementChild).toBe(document.getElementById('settings-form'))
  })
})

describe('settings frame and group', () => {
  it('draws a section body under the mockup rules, its state and refusal in the heading', () => {
    render(<SettingsFrame id="general" label="Général" desc="Identité." aside={<span data-testid="aside" />} error="Refusé"><p>new</p></SettingsFrame>)
    expect(screen.getByText('new').parentElement).toHaveClass('settings-body')
    const general = document.getElementById('set-sec-general')
    expect(general).toHaveAttribute('aria-labelledby', 'set-title-general')
    expect(general.querySelector('.panel-heading')).toContainElement(screen.getByTestId('aside'))
    expect(screen.getByRole('alert')).toHaveTextContent('Refusé')
  })

  it('draws a group with its legend, its sentence, a grid of fields or a stack of blocks', () => {
    const { container } = render(<>
      <SettingsGroup legend="Instance" hint="Ce que fait le groupe."><div className="field" /></SettingsGroup>
      <SettingsGroup legend="État" grid={false}><dl /></SettingsGroup>
    </>)
    const [fields, blocks] = container.querySelectorAll('fieldset.settings-group')
    expect(fields.querySelector('legend')).toHaveTextContent('Instance')
    expect(fields.querySelector('.group-hint')).toHaveTextContent('Ce que fait le groupe.')
    expect(fields.querySelector('.settings-grid > .field')).not.toBeNull()
    expect(blocks.querySelector('.settings-stack > dl')).not.toBeNull()
    expect(blocks.querySelector('.group-hint')).toBeNull()
  })
})

describe('settings test', () => {
  it('shows the hint at rest, then the outcome announced in its tone', () => {
    const onTest = vi.fn()
    const { rerender } = render(<SettingsTest id="email" label="Tester" hint="Avec les valeurs enregistrées." onTest={onTest} />)
    expect(document.getElementById('test-result-email')).toHaveClass('test-result', 'muted')
    fireEvent.click(screen.getByRole('button', { name: 'Tester' }))
    expect(onTest).toHaveBeenCalled()
    rerender(<SettingsTest id="email" label="Tester" busy onTest={onTest} result={{ ok: true, text: 'Envoyé.' }} />)
    expect(screen.getByRole('button', { name: 'Tester' })).toBeDisabled()
    expect(screen.getByRole('status')).toHaveTextContent('Envoyé.')
    expect(screen.getByRole('status')).toHaveClass('good')
  })
})

describe('settings save bar', () => {
  it('saves by its button outside any form, and names the pending fields or counts them', () => {
    const onSave = vi.fn()
    const onReset = vi.fn()
    const { rerender } = render(<SettingsSaveBar dirty pending={['Port']} onSave={onSave} onReset={onReset} announce="Enregistré." />)
    expect(screen.getByRole('button', { name: 'common.save' })).toHaveAttribute('type', 'button')
    fireEvent.click(screen.getByRole('button', { name: 'common.save' }))
    fireEvent.click(screen.getByRole('button', { name: 'sectioned.undo' }))
    expect(onSave).toHaveBeenCalledTimes(1)
    expect(onReset).toHaveBeenCalledTimes(1)
    expect(document.getElementById('settings-state')).toHaveTextContent('sectioned.pendingFields {"fields":"Port"}')
    expect(document.getElementById('settings-savebar')).toHaveClass('dirty')
    expect(document.getElementById('settings-announce')).toHaveTextContent('Enregistré.')
    rerender(<SettingsSaveBar dirty count={3} sections={['SMTP']} onSave={onSave} />)
    expect(document.getElementById('settings-state')).toHaveTextContent('sectioned.pendingCount {"count":3,"sections":"SMTP"}')
    rerender(<SettingsSaveBar dirty={false} lastSaved={{ at: '6 nov.' }} onSave={onSave} />)
    expect(screen.getByRole('button', { name: 'common.save' })).toBeDisabled()
    expect(document.getElementById('settings-state')).toHaveTextContent('sectioned.lastSaved {"date":"6 nov."}')
  })
})

describe('settings table of contents', () => {
  const sections = [{ id: 'general', label: 'Général', icon: 'settings' }, { id: 'email', label: 'SMTP', icon: 'send' }]
  it('links each entry to the address the page gives, the mockup anchor otherwise', () => {
    const { rerender } = render(<SettingsToc sections={sections} label="Sections" />)
    expect(screen.getByRole('link', { name: /SMTP/ })).toHaveAttribute('href', '#set-sec-email')
    rerender(<SettingsToc sections={sections} label="Sections" current="email" hrefFor={(id) => `/settings?tab=${id}`} />)
    expect(screen.getByRole('link', { name: /SMTP/ })).toHaveAttribute('href', '/settings?tab=email')
    expect(screen.getByRole('link', { name: /SMTP/ })).toHaveAttribute('aria-current', 'true')
  })

  it('jumps from the phone select and tells the page', () => {
    const onJump = vi.fn()
    render(<><SettingsJump sections={sections} onJump={onJump} /><SettingsFrame id="email" label="SMTP"><p>x</p></SettingsFrame></>)
    fireEvent.change(screen.getByLabelText('sectioned.jumpLabel'), { target: { value: 'email' } })
    expect(document.activeElement).toBe(document.getElementById('set-title-email'))
    expect(onJump).toHaveBeenCalledWith('email')
  })
})

describe('settings table of contents taller than the page', () => {
  const many = Array.from({ length: 19 }, (_, i) => ({ id: `s${i}`, label: `Section ${i}`, icon: 'settings' }))
  const layout = (current) => <SettingsLayout toc={<SettingsToc sections={many} label="Sections" current={current} />}><p>x</p></SettingsLayout>

  it('keeps to the height the page shows, less the scroll area\'s bottom padding, and follows its resize', () => {
    render(layout())
    const view = document.getElementById('view-scroll')
    const toc = document.getElementById('settings-toc')
    view.style.paddingBottom = '24px'
    Object.defineProperty(view, 'clientHeight', { configurable: true, value: 600 })
    fireEvent(window, new Event('resize'))
    expect(toc.style.maxHeight).toBe('576px')
    Object.defineProperty(view, 'clientHeight', { configurable: true, value: 400 })
    fireEvent(window, new Event('resize'))
    expect(toc.style.maxHeight).toBe('376px')
  })

  it('scrolls itself to the entry shown when it lies past its edge, and leaves it when it is in view', () => {
    const { rerender } = render(layout('s0'))
    const toc = document.getElementById('settings-toc')
    toc.scrollTo = vi.fn()
    Object.defineProperty(toc, 'clientHeight', { configurable: true, value: 300 })
    const link = (id) => toc.querySelector(`[data-jump="${id}"]`)
    many.forEach((s, i) => {
      Object.defineProperty(link(s.id), 'offsetTop', { configurable: true, value: i * 38 })
      Object.defineProperty(link(s.id), 'offsetHeight', { configurable: true, value: 36 })
    })
    rerender(layout('s18'))
    expect(toc.scrollTo).toHaveBeenLastCalledWith(expect.objectContaining({ top: 18 * 38 + 36 - 300 + 8 }))
    toc.scrollTop = 18 * 38 + 36 - 300 + 8
    toc.scrollTo.mockClear()
    rerender(layout('s17'))
    expect(toc.scrollTo).not.toHaveBeenCalled()
    rerender(layout('s1'))
    expect(toc.scrollTo).toHaveBeenLastCalledWith(expect.objectContaining({ top: 38 - 8 }))
  })
})

describe('jumpTo', () => {
  it('lands a link quietly: the title holds the focus without its outline until it loses it', () => {
    render(<SettingsFrame id="email" label="SMTP"><button type="button">next</button></SettingsFrame>)
    const title = document.getElementById('set-title-email')
    jumpTo('email', { quiet: true })
    expect(document.activeElement).toBe(title)
    expect(title).toHaveAttribute('data-quiet-focus')
    screen.getByRole('button', { name: 'next' }).focus()
    expect(title).not.toHaveAttribute('data-quiet-focus')
    jumpTo('email')
    expect(title).not.toHaveAttribute('data-quiet-focus')
  })
})
