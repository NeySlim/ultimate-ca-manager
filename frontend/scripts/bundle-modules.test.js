import { describe, it, expect } from 'vitest'
import { collectModules, relativeId } from './bundle-modules.js'

const ROOT = '/work/frontend'

function chunk(fileName, modules, css = []) {
  return { type: 'chunk', fileName, modules, viteMetadata: { importedCss: new Set(css) } }
}

describe('bundle modules record', () => {
  it('keeps a module with rendered code and drops a tree-shaken one', () => {
    const rec = collectModules({
      a: chunk('assets/vendor.js', {
        [`${ROOT}/node_modules/react/index.js`]: { renderedLength: 120 },
        [`${ROOT}/node_modules/xmlhttprequest-ssl/lib/XMLHttpRequest.js`]: { renderedLength: 0 },
      }),
    }, ROOT)
    const byId = Object.fromEntries(rec.modules.map(m => [m.id, m]))
    expect(byId['node_modules/react/index.js'].emitted).toBe(true)
    expect(byId['node_modules/react/index.js'].chunks).toEqual(['assets/vendor.js'])
    expect(byId['node_modules/xmlhttprequest-ssl/lib/XMLHttpRequest.js'].emitted).toBe(false)
  })

  it('counts a CSS module as emitted into its CSS asset', () => {
    const rec = collectModules({
      a: chunk('assets/index.js', { [`${ROOT}/node_modules/sonner/dist/styles.css`]: { renderedLength: 0 } },
        ['assets/index.css']),
    }, ROOT)
    expect(rec.modules[0]).toMatchObject({ emitted: true, chunks: ['assets/index.js', 'assets/index.css'] })
  })

  it('never writes an absolute path, virtual ids included', () => {
    const rec = collectModules({
      a: chunk('assets/x.js', {
        [`\0/elsewhere/shared/node_modules/react/index.js?commonjs-module`]: { renderedLength: 5 },
        [`/elsewhere/shared/node_modules/@radix-ui/react-tabs/dist/index.mjs`]: { renderedLength: 5 },
        [`${ROOT}/src/main.jsx`]: { renderedLength: 5 },
        ['\0vite/preload-helper.js']: { renderedLength: 5 },
        ['/somewhere/else/outside.js']: { renderedLength: 5 },
      }),
    }, ROOT)
    const ids = rec.modules.map(m => m.id)
    expect(ids).toContain('node_modules/react/index.js')
    expect(ids).toContain('node_modules/@radix-ui/react-tabs/dist/index.mjs')
    expect(ids).toContain('src/main.jsx')
    expect(ids).toContain('vite/preload-helper.js')
    for (const id of ids) expect(id.startsWith('/')).toBe(false)
    expect(JSON.stringify(rec)).not.toContain('/elsewhere')
    expect(JSON.stringify(rec)).not.toContain('/work/')
  })

  it('keeps the parent path of a nested package, shared checkout included', () => {
    const nested = 'node_modules/mdast-util-find-and-replace/node_modules/escape-string-regexp/index.js'
    expect(relativeId(`${ROOT}/${nested}`, ROOT)).toEqual({ id: nested, virtual: false })
    expect(relativeId(`\0/elsewhere/shared/${nested}?commonjs-module`, ROOT)).toEqual({ id: nested, virtual: true })
  })

  it('skips assets, which carry no modules', () => {
    const rec = collectModules({ f: { type: 'asset', fileName: 'fonts/Inter-Regular.woff2' } }, ROOT)
    expect(rec.modules).toEqual([])
  })

  it('reads a query-suffixed id by its path', () => {
    expect(relativeId(`${ROOT}/node_modules/a/b.css?inline`, ROOT)).toEqual({ id: 'node_modules/a/b.css', virtual: false })
  })
})
