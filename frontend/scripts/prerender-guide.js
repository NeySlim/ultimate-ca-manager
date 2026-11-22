// The guide's chapters drawn at build time, for the server to send already in the page
// (a browser's reader view decides at load): run by `npm run build` after `vite build`.
// Writes dist/guide-prerender/<lang>/<chapter>.html, index.html with the chapter in #root;
// the server sends them to a valid session only (backend/api/ui_routes.py), never as files.
import fs from 'fs'
import path from 'path'
import { fileURLToPath, pathToFileURL } from 'url'

export const PRERENDER_DIR = 'guide-prerender'

const escapeHtml = (s) => String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')

function replaceOnce(text, pattern, replacement, what) {
  const found = text.match(new RegExp(pattern.source, `${pattern.flags.replace('g', '')}g`)) || []
  if (found.length !== 1) throw new Error(`guide prerender: index.html has ${found.length} ${what}, one expected`)
  return text.replace(pattern, () => replacement)
}

/** index.html with the chapter drawn in #root, the tab titled, og:title the chapter's, lang the language served. */
export function chapterPage(template, { lang, chapter, html, title, chapterTitle }) {
  let page = replaceOnce(template, /<html\b[^>]*>/, `<html lang="${escapeHtml(lang)}">`, '<html> tags')
  page = replaceOnce(page, /<title>[^<]*<\/title>/,
    `<title>${escapeHtml(title)}</title>\n    <meta property="og:title" content="${escapeHtml(chapterTitle)}" />`, '<title> tags')
  return replaceOnce(page, /<div id="root"><\/div>/,
    `<div id="root" data-guide="${escapeHtml(`${lang}/${chapter}`)}">${html}</div>`, 'empty #root containers')
}

async function main() {
  const started = Date.now()
  const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
  const dist = path.join(root, 'dist')
  const work = path.join(root, '.ssr-guide')
  const template = fs.readFileSync(path.join(dist, 'index.html'), 'utf8')
  const { build } = await import('vite')
  await build({
    root,
    configFile: path.join(root, 'vite.config.js'),
    logLevel: 'warn',
    build: { ssr: 'src/ssr/guideServer.jsx', outDir: work, emptyOutDir: true, copyPublicDir: false },
  })
  try {
    const { LANGUAGES, CHAPTERS, renderChapter } = await import(pathToFileURL(path.join(work, 'guideServer.js')).href)
    const out = path.join(dist, PRERENDER_DIR)
    fs.rmSync(out, { recursive: true, force: true })
    let bytes = 0
    for (const lang of LANGUAGES) {
      fs.mkdirSync(path.join(out, lang), { recursive: true })
      for (const chapter of CHAPTERS) {
        const drawn = await renderChapter(lang, chapter)
        if (!drawn.html.includes('id="guide-article"')) throw new Error(`guide prerender: ${lang}/${chapter} has no article`)
        const page = chapterPage(template, { lang, chapter, ...drawn })
        fs.writeFileSync(path.join(out, lang, `${chapter}.html`), page)
        bytes += Buffer.byteLength(page)
      }
    }
    const count = LANGUAGES.length * CHAPTERS.length
    console.log(`guide prerender: ${count} pages, ${(bytes / 1048576).toFixed(1)} MB, ${((Date.now() - started) / 1000).toFixed(1)} s`)
  } finally {
    fs.rmSync(work, { recursive: true, force: true })
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main().catch((e) => {
    console.error(e)
    process.exit(1)
  })
}
