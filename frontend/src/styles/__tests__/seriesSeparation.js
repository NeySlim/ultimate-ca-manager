// Colour distance of chart series as people with a colour vision deficiency see them: Machado (2009)
// simulation at full severity on linear sRGB, then CIEDE2000 between the simulated colours.
import { hexToRgb } from '../../lib/__tests__/themeTokensParser'

export const VISIONS = {
  normal: [[1, 0, 0], [0, 1, 0], [0, 0, 1]],
  protan: [[0.152286, 1.052583, -0.204868], [0.114503, 0.786281, 0.099216], [-0.003882, -0.048116, 1.051998]],
  deutan: [[0.367322, 0.860646, -0.227968], [0.280085, 0.672501, 0.047413], [-0.01182, 0.04294, 0.968881]],
  tritan: [[1.255528, -0.076749, -0.178779], [-0.078411, 0.930809, 0.147602], [0.004733, 0.691367, 0.3039]],
}

const toLinear = (c) => { const v = c / 255; return v <= 0.04045 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4 }

function simulate(hex, m) {
  const l = hexToRgb(hex).map(toLinear)
  return m.map((row) => Math.min(1, Math.max(0, row[0] * l[0] + row[1] * l[1] + row[2] * l[2])))
}

function lab([r, g, b]) {
  const x = (0.4124 * r + 0.3576 * g + 0.1805 * b) / 0.95047
  const y = 0.2126 * r + 0.7152 * g + 0.0722 * b
  const z = (0.0193 * r + 0.1192 * g + 0.9505 * b) / 1.08883
  const f = (t) => (t > 0.008856 ? Math.cbrt(t) : 7.787 * t + 16 / 116)
  return [116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))]
}

const rad = (d) => (d * Math.PI) / 180
const deg = (r) => ((r * 180) / Math.PI + 360) % 360

export function deltaE2000([L1, a1, b1], [L2, a2, b2]) {
  const cb = (Math.hypot(a1, b1) + Math.hypot(a2, b2)) / 2
  const g = 0.5 * (1 - Math.sqrt(cb ** 7 / (cb ** 7 + 25 ** 7)))
  const a1p = (1 + g) * a1
  const a2p = (1 + g) * a2
  const c1 = Math.hypot(a1p, b1)
  const c2 = Math.hypot(a2p, b2)
  const h1 = deg(Math.atan2(b1, a1p))
  const h2 = deg(Math.atan2(b2, a2p))
  let dh = h2 - h1
  if (c1 * c2 === 0) dh = 0
  else if (dh > 180) dh -= 360
  else if (dh < -180) dh += 360
  const dH = 2 * Math.sqrt(c1 * c2) * Math.sin(rad(dh / 2))
  const lb = (L1 + L2) / 2
  const cbp = (c1 + c2) / 2
  let hb = h1 + h2
  if (c1 * c2 !== 0) hb = Math.abs(h1 - h2) <= 180 ? (h1 + h2) / 2 : (h1 + h2 + (h1 + h2 < 360 ? 360 : -360)) / 2
  const t = 1 - 0.17 * Math.cos(rad(hb - 30)) + 0.24 * Math.cos(rad(2 * hb)) + 0.32 * Math.cos(rad(3 * hb + 6)) - 0.2 * Math.cos(rad(4 * hb - 63))
  const rc = 2 * Math.sqrt(cbp ** 7 / (cbp ** 7 + 25 ** 7))
  const rt = -Math.sin(rad(60 * Math.exp(-(((hb - 275) / 25) ** 2)))) * rc
  const sl = 1 + (0.015 * (lb - 50) ** 2) / Math.sqrt(20 + (lb - 50) ** 2)
  const sc = 1 + 0.045 * cbp
  const sh = 1 + 0.015 * cbp * t
  const dl = (L2 - L1) / sl
  const dc = (c2 - c1) / sc
  const dhs = dH / sh
  return Math.sqrt(dl ** 2 + dc ** 2 + dhs ** 2 + rt * dc * dhs)
}

/** The smallest CIEDE2000 distance between any two of `colours` as `vision` sees them. */
export function minSeparation(colours, vision) {
  const seen = colours.map((c) => lab(simulate(c, VISIONS[vision])))
  let min = Infinity
  for (let i = 0; i < seen.length; i += 1) for (let j = i + 1; j < seen.length; j += 1) min = Math.min(min, deltaE2000(seen[i], seen[j]))
  return min
}
