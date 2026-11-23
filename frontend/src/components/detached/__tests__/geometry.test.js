/** The detached windows stay inside the visible area, never under their minimum size. */
import { describe, it, expect } from 'vitest'
import { MIN_H, MIN_W, STEP, cascadeRect, clampRect, keyRect, maxRect, resizeRect } from '../geometry'

const view = { w: 1400, h: 900 }

describe('detached window geometry', () => {
  it('brings a window back inside a narrower viewport, shrinking it only when it must', () => {
    expect(clampRect({ x: 1200, y: 700, w: 600, h: 400 }, view)).toEqual({ x: 800, y: 500, w: 600, h: 400 })
    expect(clampRect({ x: 50, y: 40, w: 600, h: 400 }, { w: 500, h: 300 })).toEqual({ x: 0, y: 0, w: 500, h: 300 })
    expect(clampRect({ x: -30, y: -10, w: 100, h: 50 }, view)).toEqual({ x: 0, y: 0, w: MIN_W, h: MIN_H })
  })

  it('cascades the windows it opens, each down and right of the one before', () => {
    const a = cascadeRect(0, { w: 600, h: 500 }, view)
    const b = cascadeRect(1, { w: 600, h: 500 }, view)
    expect(b.x - a.x).toBeGreaterThan(0)
    expect(b.y - a.y).toBe(b.x - a.x)
  })

  it('resizes from an edge or a corner, the opposite edges staying put', () => {
    const r = { x: 100, y: 100, w: 500, h: 400 }
    expect(resizeRect(r, 'e', 50, 0, view)).toEqual({ x: 100, y: 100, w: 550, h: 400 })
    expect(resizeRect(r, 'w', 50, 0, view)).toEqual({ x: 150, y: 100, w: 450, h: 400 })
    expect(resizeRect(r, 'nw', -40, -30, view)).toEqual({ x: 60, y: 70, w: 540, h: 430 })
    // Never under the minimum: the moving edge stops where the minimum leaves it
    expect(resizeRect(r, 'w', 400, 0, view)).toEqual({ x: 600 - MIN_W, y: 100, w: MIN_W, h: 400 })
    // Never past the viewport
    expect(resizeRect(r, 'se', 2000, 2000, view)).toEqual({ x: 100, y: 100, w: 1300, h: 800 })
  })

  it('moves with the arrows and resizes with Shift and the arrows, inside the viewport', () => {
    const r = { x: 100, y: 100, w: 500, h: 400 }
    expect(keyRect(r, 'ArrowRight', false, view)).toEqual({ ...r, x: 100 + STEP })
    expect(keyRect(r, 'ArrowUp', false, view)).toEqual({ ...r, y: 100 - STEP })
    expect(keyRect(r, 'ArrowRight', true, view)).toEqual({ ...r, w: 500 + STEP })
    expect(keyRect(r, 'ArrowUp', true, view)).toEqual({ ...r, h: 400 - STEP })
    expect(keyRect({ ...r, x: 0 }, 'ArrowLeft', false, view).x).toBe(0)
    expect(keyRect(r, 'Enter', false, view)).toBeNull()
  })

  it('maximizes into the work area, inside the margins of the stage at that width', () => {
    const area = { x: 0, y: 62, w: 1440, h: 813 }
    expect(maxRect(area, 1440)).toEqual({ x: 24, y: 86, w: 1392, h: 765 })
    // The stage's margins follow the mockup: 18 px up to 1000 px, 34 px from 1800 px
    expect(maxRect({ x: 0, y: 62, w: 1000, h: 613 }, 1000)).toEqual({ x: 18, y: 80, w: 964, h: 577 })
    expect(maxRect({ x: 0, y: 62, w: 1920, h: 993 }, 1920)).toEqual({ x: 34, y: 96, w: 1852, h: 925 })
  })

  it('past 1920 px, maximizes and opens inside the page held at 1852 px and centred', () => {
    // The side margins are what the page measure leaves; above and below, the mockup's 34 px
    expect(maxRect({ x: 0, y: 62, w: 3440, h: 1353 }, 3440)).toEqual({ x: 794, y: 96, w: 1852, h: 1285 })
    expect(maxRect({ x: 0, y: 62, w: 2560, h: 1353 }, 2560)).toEqual({ x: 354, y: 96, w: 1852, h: 1285 })
    // A window opens where it opens on a 1920 px page, moved with the page
    const at1920 = cascadeRect(0, { w: 600, h: 500 }, { w: 1920, h: 1000 })
    expect(cascadeRect(0, { w: 600, h: 500 }, { w: 3440, h: 1000 })).toEqual({ ...at1920, x: at1920.x + 760 })
    expect(cascadeRect(0, { w: 600, h: 500 }, { w: 1880, h: 1000 })).toEqual(cascadeRect(0, { w: 600, h: 500 }, { w: 1440, h: 1000 }))
  })
})
