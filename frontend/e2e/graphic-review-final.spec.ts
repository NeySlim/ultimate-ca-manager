import { test, expect, uid } from './support/fixtures'
import { PALETTES, usePalette, expectPalette } from './support/themes'

// The last defects of the graphic review, measured in the browser: the navigation's count of certificates due,
// the muted pills, in the four palettes (4.5:1, WCAG 1.4.3), and the e-mail settings' Azure link beside its steps
type Box = { x: number; y: number; width: number; height: number }

// Contrast of each element's words on its ground: the backgrounds under it composed up to the first opaque one
async function contrasts(page, selector: string) {
  return page.locator(selector).evaluateAll((els) => {
    // rgb()/rgba(), or color(srgb r g b / a) as a color-mix() computes
    const parse = (c: string) => {
      const srgb = c.match(/color\(srgb ([^)]+)\)/)
      const m = srgb || c.match(/rgba?\(([^)]+)\)/)
      if (!m) return [0, 0, 0, 0]
      const v = m[1].split(/[\s,/]+/).filter(Boolean).map(Number)
      const k = srgb ? 255 : 1
      return [v[0] * k, v[1] * k, v[2] * k, v.length > 3 ? v[3] : 1]
    }
    const over = (a: number[], b: number[]) => {
      const al = a[3] + b[3] * (1 - a[3])
      return [0, 1, 2].map((i) => (a[i] * a[3] + b[i] * b[3] * (1 - a[3])) / (al || 1)).concat(al)
    }
    const lum = (c: number[]) => {
      const ch = (v: number) => { const s = v / 255; return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4 }
      return 0.2126 * ch(c[0]) + 0.7152 * ch(c[1]) + 0.0722 * ch(c[2])
    }
    return els.filter((el) => (el as HTMLElement).offsetParent !== null).map((el) => {
      const layers: number[][] = []
      let unknown = false
      for (let a: Element | null = el; a; a = a.parentElement) {
        const cs = getComputedStyle(a)
        if (cs.backgroundImage !== 'none') { unknown = true; break }
        const c = parse(cs.backgroundColor)
        if (c[3] > 0) { layers.push(c); if (c[3] >= 1) break }
      }
      let ground = [255, 255, 255, 1]
      for (let i = layers.length - 1; i >= 0; i--) ground = over(layers[i], ground)
      const ink = over(parse(getComputedStyle(el).color), ground)
      const [x, y] = [lum(ink), lum(ground)]
      return { text: (el.textContent || '').trim(), unknown, ratio: (Math.max(x, y) + 0.05) / (Math.min(x, y) + 0.05) }
    })
  })
}

for (const [family, mode] of PALETTES) {
  test.describe(`${family} ${mode}`, () => {
    test.use({ viewport: { width: 1600, height: 1000 } })

    test('the count of certificates due on the navigation keeps 4.5:1', async ({ page, api }) => {
      await usePalette(page, family, mode)
      await page.route('**/api/v2/certificates/stats', async (route) => {
        const response = await route.fetch()
        const body = await response.json()
        await route.fulfill({ response, json: { ...body, data: { ...(body?.data || {}), expiring: 65, expired: 0 } } })
      })
      await page.goto('/policies')
      await expectPalette(page, family, mode)
      const count = page.locator('.main-nav .nav-count')
      await expect(count).toHaveText('65')
      const [measured] = await contrasts(page, '.main-nav .nav-count')
      expect(measured.unknown).toBe(false)
      expect(measured.ratio).toBeGreaterThanOrEqual(4.5)
    })

    test('a muted pill keeps 4.5:1 on an opened row, a hovered row and in the inspector', async ({ page, api }) => {
      const names = [uid('muted-a'), uid('muted-b')]
      for (const name of names) await api.post('/policies', { name, operations: ['issuance'], priority: 1, is_active: false })
      await usePalette(page, family, mode)
      await page.goto('/policies')
      await expectPalette(page, family, mode)
      const row = (name: string) => page.getByRole('main').getByRole('row').filter({ hasText: name })
      await row(names[0]).locator('.entity-name').click()
      await expect(row(names[0])).toHaveClass(/opened/)
      await row(names[1]).locator('td').last().hover()
      // Aurore draws the opened and hovered rows in gradients, whose grounds are measured from the tokens (mutedBadgeContrast.test.js)
      const opened = await contrasts(page, 'tbody tr.opened .badge.muted')
      const hovered = await contrasts(page, 'tbody tr:hover .badge.muted')
      expect(opened).toHaveLength(1)
      expect(hovered).toHaveLength(1)
      if (family === 'atelier') expect([opened[0].unknown, hovered[0].unknown]).toEqual([false, false])
      const measured = await contrasts(page, '.badge.muted')
      for (const m of measured.filter((x) => !x.unknown)) expect(m.ratio, m.text).toBeGreaterThanOrEqual(4.5)
    })
  })
}

for (const width of [1600, 3440]) {
  test.describe(`e-mail settings at ${width}`, () => {
    test.use({ viewport: { width, height: 1200 } })

    test('the Azure console link stands under the steps, clear of their text', async ({ page, api }) => {
      await page.goto('/settings?tab=email')
      await page.locator('#set-smtp_auth_method').selectOption('oauth2')
      await page.getByRole('button', { name: 'Outlook.com (personal)', exact: true }).click()
      const notice = page.locator('.notice').filter({ hasText: 'one-time Azure setup' })
      await expect(notice).toBeVisible()
      const link = notice.locator('a.text-link')
      const l = await link.boundingBox() as Box
      // The steps' text node as a whole (the box a reader of overlaps compares) and line by line
      const steps = await notice.locator('.pre-line').evaluate((el) => {
        const r = document.createRange()
        r.selectNodeContents(el)
        const all = r.getBoundingClientRect()
        return { bottom: all.bottom, left: all.left, right: all.right, lines: [...r.getClientRects()].map((c) => ({ top: c.top, bottom: c.bottom, left: c.left, right: c.right })) }
      })
      for (const line of steps.lines) {
        const apart = line.right <= l.x + 0.5 || line.left >= l.x + l.width - 0.5 || line.bottom <= l.y + 0.5 || line.top >= l.y + l.height - 0.5
        expect(apart).toBe(true)
      }
      expect(l.y).toBeGreaterThanOrEqual(steps.bottom - 0.5)
      expect(Math.abs(l.x - steps.left)).toBeLessThanOrEqual(1)
    })
  })
}
