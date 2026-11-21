import { test, expect, createCA, issueCert, uid, type Api } from './support/fixtures'
import { MODULES, REDIRECTS, MAIN_IDS, menuLabelKey } from '../src/navigation/registry.js'
import { readFileSync } from 'node:fs'

const en = JSON.parse(readFileSync(new URL('../src/i18n/locales/en.json', import.meta.url), 'utf8'))

// Every route the registry declares, detail routes with an object the test creates
type Route = { module: string; path: string }
const ROUTES: Route[] = MODULES.flatMap(m => [m.path, ...m.paths].map(path => ({ module: m.id, path })))

const DETAIL: Record<string, (api: Api) => Promise<{ id: number; name: string }>> = {
  '/certificates/:id': async api => {
    const cert = await issueCert(api, (await createCA(api)).id)
    return { id: cert.id, name: cert.common_name }
  },
  '/cas/:id': async api => {
    const ca = await createCA(api)
    return { id: ca.id, name: ca.common_name }
  },
  '/truststore/:id': async api => {
    const cert = await issueCert(api, (await createCA(api)).id)
    const name = uid('trusted')
    const entry = await api.post('/truststore', { name, certificate_pem: cert.pem, purpose: 'custom' })
    return { id: entry.id, name }
  },
}

const translate = (key: string) => key.split('.').reduce((o: any, k) => o?.[k], en) as string | undefined

test('the routes of the registry are all covered here', () => {
  const params = ROUTES.filter(r => r.path.includes(':')).map(r => r.path)
  expect(params.sort()).toEqual(Object.keys(DETAIL).sort())
})

for (const route of ROUTES) {
  test(`route ${route.path} (${route.module}) opens without error`, async ({ page, api, consoleErrors }) => {
    let path = route.path
    let detail: { id: number; name: string } | undefined
    if (path.includes(':')) {
      detail = await DETAIL[path](api)
      path = path.replace(/:[^/]+/, String(detail.id))
    }
    await page.goto(path)

    const heading = page.getByRole('heading', { level: 1 })
    await expect(heading).toBeVisible()
    // An emptied or missing translation shows as nothing or as its key
    await expect(heading).toHaveText(/\S/)
    await expect(heading).not.toHaveText(/^[a-z]+(\.[a-zA-Z0-9_]+)+$/)
    // The admin is never sent away from a route of the registry; a detail route
    // opens its object in the inspector over the module's list
    const landing = detail ? route.path.replace(/\/:[^/]+$/, '') : path
    await expect(page).toHaveURL(url => url.pathname === landing || url.pathname === path)
    if (detail && route.path.startsWith('/cas/')) {
      // An authority opens in the Authorities page, in the panel beside its hierarchy
      await expect(page).toHaveURL(new RegExp(`[?&]authority=${detail.id}`))
      await expect(page.getByRole('complementary', { name: detail.name })).toBeVisible()
    } else if (detail) {
      await expect(page.getByRole('tabpanel', { name: detail.name }).getByRole('heading', { name: detail.name })).toBeVisible()
    }
    await expect(page.getByRole('heading', { name: 'Something went wrong' })).toHaveCount(0)
    await page.waitForLoadState('networkidle')
    expect(consoleErrors).toEqual([])
  })
}

for (const redirect of REDIRECTS) {
  test(`legacy URL ${redirect.from} lands on ${redirect.to}`, async ({ page, api }) => {
    await page.goto(redirect.from)
    const [pathname, search] = redirect.to.split('?')
    await expect(page).toHaveURL(url => url.pathname === pathname && url.search === (search ? `?${search}` : ''))
    await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
  })
}

test('the Modules menu offers every grouped module but the main pages, under its translated label', async ({ page, api }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Modules' }).click()
  const menu = page.getByRole('navigation', { name: translate('shell.modulesMenuLabel') })
  const grouped = MODULES.filter(m => m.group && !MAIN_IDS.includes(m.id))
  for (const m of grouped) {
    const label = translate(menuLabelKey(m))
    expect(label, `${menuLabelKey(m)} has an English text`).toBeTruthy()
    expect(translate(m.descKey), `${m.descKey} has an English text`).toBeTruthy()
    // The link reads its label then the line that says what the page is for
    await expect(menu.locator(`a[data-module="${m.id}"] strong`)).toHaveText(label!)
    await expect(menu.locator(`a[data-module="${m.id}"]`)).toHaveAttribute('href', m.path)
  }
  // The main pages are links of the bar, not of the menu
  for (const id of MAIN_IDS) await expect(menu.locator(`a[data-module="${id}"]`)).toHaveCount(0)
  const bar = page.getByRole('navigation', { name: 'Main navigation' })
  await expect(bar.getByRole('link', { name: translate('shell.bar.activity'), exact: true })).toHaveAttribute('href', '/audit')
  // A module opens from the menu
  const target = grouped.find(m => m.id === 'templates')!
  await menu.locator(`a[data-module="${target.id}"]`).click()
  await expect(page).toHaveURL(new RegExp(`${target.path}$`))
  await expect(page.getByRole('heading', { level: 1, name: translate('common.templates') })).toBeVisible()
})
