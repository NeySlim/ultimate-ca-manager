import { expect, type Page } from '@playwright/test'

/** The four palettes, Atelier dark first: the one the others are measured against. */
export const PALETTES = [['atelier', 'dark'], ['atelier', 'light'], ['aurore', 'dark'], ['aurore', 'light']] as const

/**
 * The palette a page loads in: kept in the browser, and the account's own theme left out of its preferences
 * (other tests choose themes for the administrator).
 */
export async function usePalette(page: Page, family: string, mode: string) {
  await page.route('**/api/v2/account/preferences', async (route) => {
    if (route.request().method() !== 'GET') return route.continue()
    const response = await route.fetch()
    const body = await response.json()
    if (body && typeof body.data === 'object' && body.data) {
      delete body.data.theme_family
      delete body.data.theme_mode
    }
    await route.fulfill({ response, json: body })
  })
  await page.addInitScript(([f, m]) => {
    try { localStorage.setItem('ucm-theme-family', f); localStorage.setItem('ucm-theme-mode', m) } catch { /* noop */ }
  }, [family, mode])
}

/** Checks the page is drawn in the palette asked for. */
export async function expectPalette(page: Page, family: string, mode: string) {
  await expect(page.locator('html')).toHaveAttribute('data-theme', family)
  await expect(page.locator('html')).toHaveAttribute('data-mode', mode)
}

/** The boxes of every element each selector finds, to half a pixel, the pointer parked on the status bar (no hover). */
export async function boxes(page: Page, selectors: readonly string[]) {
  await page.mouse.move(2, (page.viewportSize()?.height ?? 900) - 2)
  await page.evaluate(() => document.fonts.ready)
  return page.evaluate((sels) => Object.fromEntries(sels.map((s) => [s, [...document.querySelectorAll(s)].map((e) => {
    const r = e.getBoundingClientRect()
    return [r.x, r.y, r.width, r.height].map((v) => Math.round(v * 2) / 2)
  })])), selectors)
}
