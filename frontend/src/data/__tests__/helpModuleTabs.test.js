/**
 * The protocol pages show their views as tabs under the head: their help, in the four languages it is
 * written in, names the tabs and no longer the View menu of the page head.
 */
import { describe, it, expect } from 'vitest'
import { helpContent } from '../helpContent'
import { helpGuides } from '../helpGuides'

const pages = import.meta.glob('../help/*/*.js', { eager: true })
const PAGES = ['acme', 'scep', 'est', 'tsa']
const TABS = { en: 'Tabs', fr: 'Onglets', ru: 'Вкладки', zh: '选项卡' }
const RETIRED = [/View menu/i, /menu Vue/i, /Меню «Вид»/, /视图菜单/, /^Views$/, /^Vues$/, /^Представления$/, /^视图$/]

const texts = (node, out = []) => {
  if (typeof node === 'string') out.push(node)
  else if (Array.isArray(node)) node.forEach((n) => texts(n, out))
  else if (node && typeof node === 'object') Object.entries(node).forEach(([k, v]) => { if (k !== 'icon') texts(v, out) })
  return out
}
const of = (lang, key) => (lang === 'en'
  ? { content: helpContent[key], guide: helpGuides[key] }
  : { content: pages[`../help/${lang}/${key}.js`].default.helpContent, guide: pages[`../help/${lang}/${key}.js`].default.helpGuides })

describe('the help of the protocol pages names their tabs', () => {
  for (const lang of Object.keys(TABS)) {
    it.each(PAGES)(`${lang}: %s`, (key) => {
      const { content, guide } = of(lang, key)
      expect(content.sections[0].title).toBe(TABS[lang])
      const all = [...texts(content), ...texts(guide)]
      for (const re of RETIRED) expect(all.filter((s) => re.test(s.trim())), String(re)).toEqual([])
      // The guide's headings follow the panel
      for (const s of texts(guide)) for (const re of [/^## Views$/m, /^## Vues$/m, /^## Представления$/m, /^## 视图$/m]) expect(re.test(s), String(re)).toBe(false)
    })
  }
})
