// Records which modules each emitted chunk carries, so the release SBOM names only the
// npm packages actually fused into dist/ (tree-shaken ones have no rendered code).
import fs from 'fs'
import path from 'path'

const CSS = /\.(css|scss|sass|less|styl|pcss|postcss)$/

// Module id as written in the record: relative to the frontend root, never an absolute path
export function relativeId(id, root) {
  let clean = String(id).split('?')[0]
  const virtual = clean.startsWith('\0')
  if (virtual) clean = clean.slice(1)
  const nm = clean.lastIndexOf('/node_modules/')
  if (nm >= 0) return { id: clean.slice(nm + 1), virtual }
  if (!path.isAbsolute(clean)) return { id: clean, virtual }
  const rel = path.relative(root, clean).split(path.sep).join('/')
  if (rel.startsWith('..')) return { id: path.basename(clean), virtual: true }
  return { id: rel, virtual }
}

export function collectModules(bundle, root) {
  const modules = {}
  for (const out of Object.values(bundle)) {
    if (out.type !== 'chunk') continue
    for (const [rawId, info] of Object.entries(out.modules || {})) {
      const { id, virtual } = relativeId(rawId, root)
      const css = CSS.test(String(rawId).split('?')[0])
      // CSS goes to a separate asset: its module renders no JavaScript but is emitted
      const emitted = (info.renderedLength || 0) > 0 || css
      const m = modules[id] || (modules[id] = { id, virtual, emitted: false, chunks: [] })
      if (emitted) {
        m.emitted = true
        m.chunks.push(out.fileName)
        for (const asset of out.viteMetadata?.importedCss || []) {
          if (css && !m.chunks.includes(asset)) m.chunks.push(asset)
        }
      }
    }
  }
  return { format: 'ucm-bundle-modules', version: 1,
    modules: Object.values(modules).sort((a, b) => a.id.localeCompare(b.id)) }
}

export default function bundleModules({ root, file }) {
  return {
    name: 'ucm-bundle-modules',
    apply: 'build',
    generateBundle(_options, bundle) {
      fs.writeFileSync(file, JSON.stringify(collectModules(bundle, root), null, 1) + '\n')
    },
  }
}
