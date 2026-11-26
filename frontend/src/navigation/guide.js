/**
 * The chapters of the guide page (/guide/:chapter), in the order and groups of the registry's
 * modules. Pure data and helpers: the help itself is loaded by data/helpEnglish.js.
 *
 * key: the entry of helpGuides (helpContent for `navigation`, which only has a quick help);
 * module: the registry module whose page the chapter describes; path: that page when it is a
 * tab of another module; group: a registry group, or 'general' for the console as a whole.
 */
import { GROUPS, MODULES, isVisible, moduleById } from './registry'

// Chapters whose key differs from their module's id, and the chapters of a settings tab
const MODULE_OF = {
  dashboard: 'dashboard', auditLogs: 'audit', crlocsp: 'crl-ocsp', usersGroups: 'users', certTools: 'tools',
  sshCas: 'ssh-cas', sshCertificates: 'ssh-certificates', sshHosts: 'ssh-hosts', systemLogs: 'logs',
  sso: 'settings', security: 'settings', msca: 'settings',
}
const TAB_OF = { sso: 'sso', security: 'security', msca: 'microsoftCA' }
// Chapters not named after a module: the label of the settings tab they describe
const LABEL_OF = { navigation: 'commands.categories.navigation', sso: 'settings.tabs.sso', security: 'settings.tabs.security', msca: 'settings.tabs.microsoftCA' }
// The console as a whole, before the groups of the registry
const GENERAL = ['navigation', 'dashboard', 'account', 'security']
// Superseded by Operations (/import redirects there): left out until the editorial pass decides
export const RETIRED_CHAPTERS = ['importExport']

const keyOf = (moduleId) => Object.keys(MODULE_OF).find((k) => MODULE_OF[k] === moduleId && !TAB_OF[k]) || moduleId

function chapter(key) {
  const module = moduleById(MODULE_OF[key] || key) || null
  const group = GENERAL.includes(key) ? 'general' : module?.group || 'general'
  const path = module && (TAB_OF[key] ? `${module.path}?tab=${TAB_OF[key]}` : module.path)
  return { key, module, path, group, labelKey: LABEL_OF[key] || module?.labelKey }
}

/** Every chapter in reading order: General first, then each group in the registry's module order. */
export const GUIDE_CHAPTERS = (() => {
  const keys = [...GENERAL]
  for (const g of GROUPS) {
    for (const m of MODULES.filter((x) => x.group === g.id)) {
      keys.push(keyOf(m.id))
      // The settings tabs follow the settings
      if (m.id === 'settings') keys.push(...Object.keys(TAB_OF).filter((k) => !GENERAL.includes(k)))
    }
  }
  return keys.map(chapter)
})()

export const GUIDE_GROUPS = [{ id: 'general', labelKey: 'guide.general' }, ...GROUPS]

/** The chapters grouped for the table of contents: [{ id, labelKey, chapters }]. */
export function guideGroups() {
  return GUIDE_GROUPS.map((g) => ({ ...g, chapters: GUIDE_CHAPTERS.filter((c) => c.group === g.id) })).filter((g) => g.chapters.length)
}

export const guideChapter = (key) => GUIDE_CHAPTERS.find((c) => c.key === key) || null

/** The page a chapter describes, when the account may open it; null otherwise. */
export function openPagePath(c, can) {
  if (!c?.module || !isVisible(c.module, can)) return null
  return c.path
}

/** The chapter a heading id belongs to (ids are `<chapter>-<slug>`), the longest key first. */
export function chapterOfAnchor(id) {
  if (!id) return null
  return [...GUIDE_CHAPTERS].sort((a, b) => b.key.length - a.key.length).find((c) => id.startsWith(`${c.key}-`)) || null
}

/** The guide's address for a help key of the console and, optionally, one of its sections. */
export function guideHref(key, section) {
  const c = guideChapter(key)
  if (!c) return '/guide'
  return `/guide/${encodeURIComponent(c.key)}${section ? `#${section}` : ''}`
}
