/**
 * The quick help's « see also »: each entry, written in English in the help data, is the chapter it names,
 * a link to it under its title in the language; a name no chapter answers stays plain text.
 */
import { describe, it, expect, vi } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'

vi.mock('react-i18next', () => ({ useTranslation: () => ({ t: (k) => `t:${k}`, i18n: { language: 'fr' } }) }))

import { QuickHelp } from '../QuickHelp'

const content = { related: ['Overview', 'Certificates', 'Settings', 'Nowhere'] }
const seeAlso = () => screen.getByText('t:help.seeAlso').closest('section')

describe('see also', () => {
  it('links each chapter under its translated title, in the guide', () => {
    render(<MemoryRouter><QuickHelp content={content} /></MemoryRouter>)
    const links = within(seeAlso()).getAllByRole('link')
    expect(links.map((a) => [a.textContent, a.getAttribute('href')])).toEqual([
      ['t:common.dashboard', '/guide/dashboard'],
      ['t:common.certificates', '/guide/certificates'],
      ['t:common.settings', '/guide/settings'],
    ])
    expect(within(seeAlso()).getByText('Nowhere').tagName).toBe('LI')
    expect(seeAlso().textContent).not.toMatch(/Overview|Settings/)
  })

  it('opens the chapters in a tab of their own from the help dialog', () => {
    render(<QuickHelp content={content} newTab />)
    const link = within(seeAlso()).getAllByRole('link')[0]
    expect(link).toHaveAttribute('target', '_blank')
    expect(link).toHaveAttribute('href', '/guide/dashboard')
  })
})
