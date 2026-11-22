import { test, expect, createCA } from './support/fixtures'

// Real geometry of the Authorities page, as the Atelier mockup draws it (its style.css, copied): jsdom measures nothing
type Box = { x: number; y: number; width: number; height: number }
const box = async (locator): Promise<Box> => {
  const b = await locator.boundingBox()
  expect(b).not.toBeNull()
  return b as Box
}
const css = (locator, prop: string) => locator.evaluate((el, p) => getComputedStyle(el).getPropertyValue(p), prop)

test.describe('desktop', () => {
  test.use({ viewport: { width: 1600, height: 1000 } })

  test('the hierarchy and the side panel keep the mockup\'s columns and cards', async ({ page, api }) => {
    const root = await createCA(api)
    await createCA(api, { parentCAId: root.id })
    await page.goto(`/cas?authority=${root.id}`)
    const main = page.getByRole('main')
    const side = main.locator('aside.ca-side')
    await expect(side).toBeVisible()

    // ca-layout: the tree takes the room left, a 330 px panel at 22 px from it
    const tree = await box(main.locator('.ca-tree-panel'))
    const panel = await box(side)
    expect(Math.round(panel.width)).toBe(330)
    expect(Math.round(panel.x - (tree.x + tree.width))).toBe(22)
    expect(Math.round(panel.y)).toBe(Math.round(tree.y))
    // A node is a 244 px card; its sub-authorities sit 44 px further right
    const card = await box(main.locator(`[data-ca="${root.id}"]`))
    expect(Math.round(card.width)).toBe(244)
    expect(await css(main.locator(`[data-ca="${root.id}"]`), 'border-top-left-radius')).toBe('5px')
    expect(await css(side.locator('h2'), 'font-size')).toBe('17px')
    // The actions are full-width buttons of at least 36 px
    const issue = await box(side.getByRole('button', { name: 'Issue with this CA' }))
    expect(issue.height).toBeGreaterThanOrEqual(36)
    expect(Math.round(issue.width)).toBe(Math.round((await box(side.locator('.ca-actions'))).width))
  })
})

test.describe('phone', () => {
  test.use({ viewport: { width: 390, height: 844 } })

  test('the panel goes under the tree, the cards take the width, nothing overflows', async ({ page, api }) => {
    const root = await createCA(api)
    await page.goto(`/cas?authority=${root.id}`)
    const main = page.getByRole('main')
    const side = main.locator('aside.ca-side')
    await expect(side).toBeVisible()
    const tree = await box(main.locator('.ca-tree-panel'))
    const panel = await box(side)
    expect(panel.y).toBeGreaterThan(tree.y + tree.height - 1)
    expect(Math.round(panel.width)).toBe(Math.round(tree.width))
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(390)
    // The head's hidden buttons stay one tap away under « ⋯ »
    await main.getByRole('button', { name: 'Page actions' }).click()
    await expect(page.getByRole('dialog', { name: 'Page actions' }).getByRole('button', { name: 'Import' })).toBeVisible()
  })
})

test.describe('a phone of 360 px', () => {
  test.use({ viewport: { width: 360, height: 800 } })

  test('the side panel cuts no word, keeps the actions out of the values, folds its help', async ({ page, api }) => {
    const root = await createCA(api)
    await page.goto(`/cas?authority=${root.id}`)
    const side = page.getByRole('main').locator('aside.ca-side')
    await expect(side.locator('.kvg dl.kv').first()).toBeVisible()
    // Every word of a term or a value on one line (a technical value in its chip wraps after its separators)
    const cut = await side.evaluate((aside) => {
      const out: string[] = []
      const cells = [...aside.querySelectorAll('.kvg dl.kv > .row > :is(dt, dd.v, dd.absent)')]
      for (const cell of cells) {
        const walker = document.createTreeWalker(cell, NodeFilter.SHOW_TEXT)
        for (let node = walker.nextNode(); node; node = walker.nextNode()) {
          if ((node.parentElement as Element).closest('.code-value')) continue
          const text = node.textContent || ''
          for (const m of text.matchAll(/\S+/g)) {
            const range = document.createRange()
            range.setStart(node, m.index!)
            range.setEnd(node, m.index! + m[0].length)
            const tops = new Set([...range.getClientRects()].filter((r) => r.width > 0).map((r) => Math.round(r.top)))
            if (tops.size > 1) out.push(m[0])
          }
        }
      }
      return out
    })
    expect(cut).toEqual([])
    expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(360)
    // The CA's signature is named by its hash, as a certificate's is
    await expect(side.locator('.row', { has: page.locator('dt', { hasText: /^Signature$/ }) }).locator('dd.v')).toHaveText(/^SHA-(256|384|512)$/)
    // The actions sit apart from the values
    await expect(side.locator('.kvg dd.v button[data-write]')).toHaveCount(0)
    await expect(side.locator('.kvg dd.act button[data-write]').first()).toBeVisible()
    // The help of « Unique subject » folded behind its button, unfolded on the whole width of the block
    const tip = side.getByRole('button', { name: 'Help: Unique subject' })
    await expect(tip).toHaveAttribute('aria-expanded', 'false')
    const helpId = await tip.getAttribute('aria-controls')
    const help = side.locator(`[id="${helpId}"]`)
    await expect(help).toBeHidden()
    await tip.click()
    await expect(help).toBeVisible()
    const block = (await side.locator('.kvg dl.kv').filter({ has: page.locator(`[id="${helpId}"]`) }).boundingBox())!
    const h = (await help.boundingBox())!
    expect(Math.abs(h.x - block.x)).toBeLessThanOrEqual(1)
  })
})
