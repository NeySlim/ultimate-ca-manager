/** Pins keep the mockup's line icons: a pinned page's icon is not filled, the pin is upright. */
import { describe, it, expect, vi } from 'vitest'
import { render } from '@testing-library/react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { PushPinSimple } from '@phosphor-icons/react'
import { tStub, canFor, ROLES } from './shellTestUtils'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: tStub, i18n: { language: 'en' } }) }))

import { PinnedModules } from '../PinnedModules'
import { ModulesMenu } from '../ModulesMenu'
import { moduleById } from '../../../navigation/registry'

const drawnOf = (Icon) => {
  const box = document.createElement('div')
  box.innerHTML = renderToStaticMarkup(<Icon size={16} />)
  return box.querySelector('svg').innerHTML
}

describe('pin icons', () => {
  it('draws the icon of an open pinned module in its line weight, as when it is closed', () => {
    const { container } = render(<MemoryRouter><PinnedModules pins={['reports']} activeId="reports" /></MemoryRouter>)
    const link = container.querySelector('a[data-module="reports"]')
    expect(link).toHaveClass('is-active')
    expect(link.querySelector('svg').innerHTML).toBe(drawnOf(moduleById('reports').icon))
  })

  it('uses the upright pin in the Modules menu', () => {
    const { container, getByRole } = render(<MemoryRouter><ModulesMenu can={canFor(ROLES.admin)} pins={['reports']} onTogglePin={() => true} activeId="" /></MemoryRouter>)
    getByRole('button', { name: /shell\.modules$/ }).click()
    const pin = container.querySelector('.shell-pin[aria-pressed="true"] svg')
    expect(pin.innerHTML).toBe(drawnOf(PushPinSimple))
  })
})
