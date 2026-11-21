/** The shell draws the mockup's pictograms: a module's own in the bar and the menu, the pin in the menu. */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { tStub, canFor, ROLES } from './shellTestUtils'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: tStub, i18n: { language: 'en' } }) }))

import { PinnedModules } from '../PinnedModules'
import { ModulesButton, ModulesMenu } from '../ModulesMenu'
import { useDisclosure } from '../useDisclosure'
import { PATHS } from '../../atelier/icons'
import { MODULES, glyphOf, moduleById } from '../../../navigation/registry'

const drawn = (name) => {
  const box = document.createElement('div')
  box.innerHTML = `<svg>${PATHS[name]}</svg>`
  return box.querySelector('svg').innerHTML
}

function Menu({ pins }) {
  const menu = useDisclosure()
  return (
    <>
      <ModulesButton menu={menu} can={canFor(ROLES.admin)} pins={pins} activeId="" />
      <ModulesMenu menu={menu} can={canFor(ROLES.admin)} pins={pins} onTogglePin={() => true} activeId="" />
    </>
  )
}

describe('shell icons', () => {
  it('gives every module a pictogram of the mockup\'s set', () => {
    for (const m of MODULES) expect(PATHS[glyphOf(m)], m.id).toBeTruthy()
    expect(glyphOf(moduleById('acme'))).toBe('refresh')
    expect(glyphOf(moduleById('approvals'))).toBe('approve')
  })

  it('draws a pinned module with its own pictogram, open or not', () => {
    const { container } = render(<MemoryRouter><PinnedModules pins={['reports']} activeId="reports" /></MemoryRouter>)
    const link = container.querySelector('a[data-module="reports"]')
    expect(link).toHaveClass('pinned-link', 'active')
    expect(link.querySelector('svg').innerHTML).toBe(drawn('chart'))
  })

  it('uses the mockup\'s pin in the Modules menu', () => {
    const { container, getByRole } = render(<MemoryRouter><Menu pins={['reports']} /></MemoryRouter>)
    getByRole('button', { name: /shell\.modules/ }).click()
    const pin = container.querySelector('.pin-btn[aria-pressed="true"] svg')
    expect(pin.innerHTML).toBe(drawn('pin'))
  })
})
