/**
 * Settings and Account (#455): the help puts the save state in the page head above the form,
 * at the bottom of the page on a phone, in every language the help is written in.
 */
import { describe, it, expect } from 'vitest'
import { helpContent } from '../helpContent'

const ABOVE = {
  en: 'In the page head, above the form',
  fr: 'en-tête de la page, au-dessus du formulaire',
  es: 'cabecera de la página, encima del formulario',
  ru: 'заголовке страницы, над формой',
  zh: '页面标题栏中、表单上方',
}
const BESIDE = /right of the title|à droite du titre|derecha del título|справа от названия|标题右侧/
const english = { settings: helpContent.settings, account: helpContent.account }
const pages = import.meta.glob('../help/*/{settings,account}.js')

const text = (page) => JSON.stringify(page.sections)
const load = async (lang, key) => (lang === 'en' ? english[key] : (await pages[`../help/${lang}/${key}.js`]()).default.helpContent)

describe('the help places the save state above the form', () => {
  for (const lang of Object.keys(ABOVE)) {
    for (const key of ['settings', 'account']) {
      it(`${lang} ${key}`, async () => {
        const page = text(await load(lang, key))
        expect(page.toLowerCase()).toContain(ABOVE[lang].toLowerCase())
        expect(page).not.toMatch(BESIDE)
      })
    }
  }
})
