import { test as base, expect, type Browser, type Page, type TestInfo } from '@playwright/test'
import { Api, ADMIN_USER, ADMIN_PASSWORD, dismissSupportCard } from './api'

export * from './api'

type Session = { page: Page; api: Api }

type Fixtures = {
  /** Opens a browser session of another user (its own context, closed after the test). */
  signIn: (username: string, password: string) => Promise<Session>
  /** API session of the administrator, shared with `page`. */
  api: Api
  /** Console errors and uncaught exceptions seen by `page`. */
  consoleErrors: string[]
}

export const test = base.extend<Fixtures>({
  page: async ({ page }, use, testInfo) => {
    await forceEnglish(page)
    await use(page)
    await dumpOnFailure(page, testInfo)
  },
  signIn: async ({ browser }, use, testInfo) => {
    const opened: Awaited<ReturnType<Browser['newContext']>>[] = []
    await use(async (username, password) => {
      const context = await browser.newContext()
      opened.push(context)
      const page = await context.newPage()
      await forceEnglish(page)
      const api = await Api.login(page.request, username, password)
      await dismissSupportCard(api)
      return { page, api }
    })
    for (const context of opened) {
      for (const page of context.pages()) await dumpOnFailure(page, testInfo)
      await context.close()
    }
  },
  consoleErrors: async ({ page }, use) => {
    const errors: string[] = []
    page.on('console', msg => { if (msg.type() === 'error') errors.push(msg.text()) })
    page.on('pageerror', err => errors.push(`pageerror: ${err.message}`))
    await use(errors)
  },
  api: async ({ page }, use) => {
    await use(await Api.login(page.request, ADMIN_USER, ADMIN_PASSWORD))
  },
})

export { expect }

// The accessibility tree of a page whose test failed, in the console log
const DUMP = process.env.UCM_E2E_DUMP !== '0'

async function dumpOnFailure(page: Page, testInfo: TestInfo) {
  if (!DUMP || testInfo.status === testInfo.expectedStatus || page.isClosed() || page.url() === 'about:blank') return
  console.log(`--- page at failure (${page.url()})\n` + await page.locator('body').ariaSnapshot().catch(e => String(e)))
}

// English unless a test chooses otherwise; the choice is kept across reloads
async function forceEnglish(page: Page) {
  await page.addInitScript(() => {
    try { if (!localStorage.getItem('i18nextLng')) localStorage.setItem('i18nextLng', 'en') } catch { /* noop */ }
  })
}

/** Opens `path` and waits for its page heading. */
export async function open(page: Page, path: string) {
  await page.goto(path)
  await expect(page.getByRole('heading', { level: 1 })).toBeVisible()
}
