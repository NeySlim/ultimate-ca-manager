/**
 * The panel merges a translated page into the English one by position, so a
 * missing or extra entry shifts every following one onto the wrong text.
 */
import { describe, it, expect } from 'vitest'
import { helpContent } from '../helpContent'

const pages = import.meta.glob('../help/*/*.js')

const LISTS = ['items', 'definitions']
const shape = (page) => (page?.sections || []).map((sec) => LISTS.map((k) => (sec[k] || []).length).join('/'))
const flat = (page) => ['tips', 'warnings'].map((k) => (page?.[k] || []).length).join('/')

describe('translated help pages follow the English entries one for one', () => {
  it.each(Object.keys(pages))('%s', async (path) => {
    const key = path.split('/').pop().replace(/\.js$/, '')
    const page = (await pages[path]()).default
    const english = helpContent[key]
    expect(english, `helpContent.${key} exists in English`).toBeTruthy()
    expect(shape(page.helpContent), 'entries per section').toEqual(shape(english))
    expect(flat(page.helpContent), 'tips/warnings').toEqual(flat(english))
  })
})
