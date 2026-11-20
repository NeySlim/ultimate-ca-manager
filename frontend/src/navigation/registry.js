/**
 * Single description of every console module: the router, the Modules menu, the
 * command palette and the page title read it. Pure data and helpers; pages are
 * bound in ./pages.js so this file never loads them.
 *
 * guard: 'auth' (signed in) | 'admin' (wildcard permission) | { permission }.
 * group: the console group (see GROUPS), null for modules outside any menu.
 * barKey: label of a page of the main bar (MAIN_IDS).
 * descKey: one line under the module in the Modules menu; menuKey: its menu and pin label when shorter.
 * paths: extra routes of the module (detail routes, aliases).
 */
// Module icons follow the mockup's (data.js): refresh, globe, plug, stamp, balance, approve, radar, users, chip, sliders, template, anchor
import {
  House, Certificate, ShieldCheck, FileText, Key, UserCircle,
  Lightning, ClockCounterClockwise, UsersThree, Shield, FileX, Vault,
  Wrench, Globe, Stamp, ChartBar, Stack, Terminal,
  ArrowClockwise, Plug, Scales, CheckCircle, Target, Users, Cpu, SlidersHorizontal, Layout, Anchor,
} from '@phosphor-icons/react'

export const GROUPS = [
  { id: 'pki', labelKey: 'common.navPki' },
  { id: 'protocols', labelKey: 'common.navProtocols' },
  { id: 'governance', labelKey: 'common.navGovernance' },
  { id: 'admin', labelKey: 'common.navAdmin' },
]

const NAV = 'commands.categories.navigation'
const PRO = 'commands.categories.proFeatures'
const GOV = 'commands.categories.governance'

// Menu order within each group is the order of this list
const RAW_MODULES = [
  { id: 'dashboard', path: '/', paths: ['/dashboard'], labelKey: 'common.dashboard', barKey: 'shell.bar.dashboard', shortKey: 'common.dashboardShort', icon: House, group: null, guard: 'auth',
    palette: { rank: 1, labelKey: 'commands.nav.dashboard', category: NAV } },
  { id: 'certificates', path: '/certificates', paths: ['/certificates/:id'], labelKey: 'common.certificates', barKey: 'shell.bar.certificates', shortKey: 'common.certificatesShort', icon: Certificate, group: 'pki', guard: 'auth', pinnable: true,
    palette: { rank: 2, labelKey: 'commands.nav.certificates', category: NAV } },
  { id: 'cas', path: '/cas', paths: ['/cas/:id'], labelKey: 'common.cas', barKey: 'shell.bar.cas', shortKey: 'common.casShort', icon: ShieldCheck, group: 'pki', guard: 'auth', pinnable: true,
    palette: { rank: 3, labelKey: 'commands.nav.cas', category: NAV } },
  { id: 'csrs', path: '/csrs', labelKey: 'common.csrs', descKey: 'shell.moduleDesc.csrs', shortKey: 'common.csrsShort', icon: FileText, group: 'pki', guard: 'auth', pinnable: true,
    palette: { rank: 4, labelKey: 'commands.nav.csrs', category: NAV } },
  { id: 'templates', path: '/templates', labelKey: 'common.templates', descKey: 'shell.moduleDesc.templates', shortKey: 'common.templatesShort', icon: Layout, group: 'pki', guard: 'auth', pinnable: true,
    palette: { rank: 5, labelKey: 'commands.nav.templates', category: NAV } },
  { id: 'ssh-cas', path: '/ssh/cas', labelKey: 'common.sshCas', descKey: 'shell.moduleDesc.sshCas', icon: Key, group: 'admin', guard: { permission: 'read:ssh_cas' }, pinnable: true,
    palette: { rank: 22, labelKey: 'commands.nav.sshCas', icon: Terminal, category: NAV } },
  { id: 'ssh-certificates', path: '/ssh/certificates', labelKey: 'common.sshCertificates', descKey: 'shell.moduleDesc.sshCertificates', icon: Certificate, group: 'admin', guard: { permission: 'read:ssh' }, pinnable: true,
    palette: { rank: 23, labelKey: 'commands.nav.sshCertificates', icon: Terminal, category: NAV } },
  { id: 'acme', path: '/acme', labelKey: 'common.acme', descKey: 'shell.moduleDesc.acme', shortKey: 'common.acmeShort', icon: ArrowClockwise, group: 'protocols', guard: { permission: 'read:acme' }, pinnable: true,
    palette: { rank: 7, labelKey: 'commands.nav.acme', category: NAV } },
  { id: 'scep', path: '/scep-config', labelKey: 'common.scep', descKey: 'shell.moduleDesc.scep', shortKey: 'common.scepShort', icon: Globe, group: 'protocols', guard: { permission: 'read:scep' }, pinnable: true,
    palette: { rank: 8, labelKey: 'commands.nav.scep', category: NAV } },
  { id: 'est', path: '/est-config', labelKey: 'common.est', descKey: 'shell.moduleDesc.est', shortKey: 'common.estShort', icon: Plug, group: 'protocols', guard: { permission: 'read:est' }, pinnable: true,
    palette: { rank: 9, labelKey: 'commands.nav.est', category: NAV } },
  { id: 'tsa', path: '/tsa-config', labelKey: 'common.tsa', descKey: 'shell.moduleDesc.tsa', icon: Stamp, group: 'protocols', guard: { permission: 'read:settings' }, pinnable: true },
  { id: 'crl-ocsp', path: '/crl-ocsp', labelKey: 'common.crlOcsp', descKey: 'shell.moduleDesc.crlOcsp', menuKey: 'shell.moduleLabel.crlOcsp', shortKey: 'common.crlOcspShort', icon: FileX, group: 'protocols', guard: { permission: 'read:crl' }, pinnable: true },
  { id: 'truststore', path: '/truststore', paths: ['/truststore/:id'], labelKey: 'common.trustStore', descKey: 'shell.moduleDesc.truststore', menuKey: 'shell.moduleLabel.truststore', shortKey: 'common.trustStoreShort', icon: Anchor, group: 'pki', guard: { permission: 'read:truststore' }, pinnable: true },
  { id: 'operations', path: '/operations', labelKey: 'common.operations', descKey: 'shell.moduleDesc.operations', shortKey: 'common.operationsShort', icon: Lightning, group: 'admin', guard: 'admin', pinnable: true,
    palette: { id: 'import', rank: 10, labelKey: 'commands.nav.operations', category: NAV } },
  { id: 'tools', path: '/tools', labelKey: 'common.tools', descKey: 'shell.moduleDesc.tools', shortKey: 'common.toolsShort', icon: Wrench, group: 'pki', guard: 'auth', pinnable: true,
    palette: { rank: 11, labelKey: 'commands.nav.tools', category: NAV } },
  { id: 'policies', path: '/policies', labelKey: 'common.policies', descKey: 'shell.moduleDesc.policies', shortKey: 'common.policiesShort', icon: Scales, group: 'governance', guard: { permission: 'read:policies' }, pinnable: true,
    palette: { rank: 19, labelKey: 'commands.nav.policies', category: GOV } },
  { id: 'approvals', path: '/approvals', labelKey: 'common.approvals', descKey: 'shell.moduleDesc.approvals', shortKey: 'common.approvalsShort', icon: CheckCircle, group: 'governance', guard: { permission: 'read:approvals' }, pinnable: true,
    palette: { rank: 20, labelKey: 'commands.nav.approvals', category: GOV } },
  { id: 'keyRecovery', path: '/key-recovery', labelKey: 'common.keyRecovery', descKey: 'shell.moduleDesc.keyRecovery', icon: Vault, group: 'governance', guard: { permission: 'read:key_recovery' }, pinnable: true },
  { id: 'reports', path: '/reports', labelKey: 'common.reports', descKey: 'shell.moduleDesc.reports', shortKey: 'common.reportsShort', icon: ChartBar, group: 'governance', guard: { permission: 'read:audit' }, pinnable: true,
    palette: { rank: 21, labelKey: 'commands.nav.reports', category: GOV } },
  { id: 'discovery', path: '/discovery', labelKey: 'common.discovery', descKey: 'shell.moduleDesc.discovery', menuKey: 'shell.moduleLabel.discovery', icon: Target, group: 'governance', guard: { permission: 'read:certificates' }, pinnable: true },
  { id: 'users', path: '/users', labelKey: 'common.users', descKey: 'shell.moduleDesc.users', shortKey: 'common.usersShort', icon: Users, group: 'admin', guard: 'admin', pinnable: true,
    palette: { rank: 6, labelKey: 'commands.nav.users', category: NAV } },
  { id: 'rbac', path: '/rbac', labelKey: 'common.rbac', descKey: 'shell.moduleDesc.rbac', shortKey: 'common.rbacShort', icon: Shield, group: 'admin', guard: 'admin', pinnable: true,
    palette: { rank: 16, labelKey: 'commands.nav.rbac', category: PRO, pro: true } },
  { id: 'hsm', path: '/hsm', labelKey: 'common.hsm', descKey: 'shell.moduleDesc.hsm', menuKey: 'shell.moduleLabel.hsm', shortKey: 'common.hsmShort', icon: Cpu, group: 'admin', guard: { permission: 'read:hsm' }, pinnable: true,
    palette: { rank: 18, labelKey: 'commands.nav.hsm', category: PRO, pro: true } },
  { id: 'audit', path: '/audit', labelKey: 'common.audit', barKey: 'shell.bar.activity', descKey: 'shell.moduleDesc.audit', shortKey: 'common.auditShort', icon: ClockCounterClockwise, group: 'admin', guard: { permission: 'read:audit' }, pinnable: true,
    palette: { rank: 12, labelKey: 'commands.nav.audit', category: NAV } },
  { id: 'logs', path: '/logs', labelKey: 'common.systemLogs', descKey: 'shell.moduleDesc.logs', icon: Stack, group: 'admin', guard: 'admin', pinnable: true },
  { id: 'user-certificates', path: '/user-certificates', labelKey: 'userCertificates.title', descKey: 'shell.moduleDesc.userCertificates', icon: Certificate, group: 'pki', guard: { permission: 'read:user_certificates' }, pinnable: true },
  { id: 'settings', path: '/settings', labelKey: 'common.settings', descKey: 'shell.moduleDesc.settings', shortKey: 'common.settingsShort', icon: SlidersHorizontal, group: 'admin', guard: 'admin', pinnable: true,
    palette: { rank: 13, labelKey: 'commands.nav.settings', category: NAV } },
  { id: 'account', path: '/account', labelKey: 'common.account', icon: UserCircle, group: null, guard: 'auth',
    palette: { rank: 14, labelKey: 'commands.nav.account', category: NAV } },
]

export const MODULES = RAW_MODULES.map(m => ({ paths: [], keywords: [], pinnable: false, ...m }))

// Legacy URLs still answered; `palette` lists the ones the command palette offers
export const REDIRECTS = [
  { from: '/import', to: '/operations' },
  { from: '/groups', to: '/users?tab=groups',
    palette: { id: 'groups', path: '/users?tab=groups', rank: 15, labelKey: 'commands.nav.groups', icon: UsersThree, category: NAV } },
  { from: '/sso', to: '/settings?tab=sso',
    palette: { id: 'sso', path: '/sso', rank: 17, labelKey: 'commands.nav.sso', icon: Key, category: PRO, pro: true } },
  { from: '/security', to: '/settings?tab=security' },
]

// Palette shortcuts that open a module (the action itself is not handled yet)
const PALETTE_ACTIONS = [
  { id: 'new-cert', labelKey: 'commands.actions.newCertificate', moduleId: 'certificates', action: 'new' },
  { id: 'new-ca', labelKey: 'commands.actions.newCA', moduleId: 'cas', action: 'new' },
  { id: 'upload-csr', labelKey: 'commands.actions.uploadCSR', moduleId: 'csrs', action: 'upload' },
]
const ACTION_CATEGORY = 'commands.categories.actions'

/** `can` is { isAdmin(), hasPermission(p) }; omitted, everything is visible. */
export function isVisible(mod, can) {
  if (!can) return true
  const { guard } = mod
  if (guard === 'admin') return !!can.isAdmin()
  if (guard && guard.permission) return !!(can.isAdmin() || can.hasPermission(guard.permission))
  return guard === 'auth'
}

export function visibleModules(can) {
  return MODULES.filter(m => isVisible(m, can))
}

/** Console groups with the modules `can` sees, empty groups dropped. */
export function groupsFor(can) {
  const visible = visibleModules(can)
  return GROUPS
    .map(g => ({ ...g, modules: visible.filter(m => m.group === g.id) }))
    .filter(g => g.modules.length > 0)
}

// Pages of the main bar, in its order: never listed in the Modules menu nor pinned
export const MAIN_IDS = ['dashboard', 'certificates', 'cas', 'audit']

/** Groups of the Modules menu: those of groupsFor without the pages of the main bar. */
export function menuGroupsFor(can) {
  return groupsFor(can)
    .map(g => ({ ...g, modules: g.modules.filter(m => !MAIN_IDS.includes(m.id)) }))
    .filter(g => g.modules.length > 0)
}

/** Label of a module in the Modules menu and the bar. */
export const menuLabelKey = (mod) => mod.menuKey || mod.labelKey

export function moduleById(id) {
  return MODULES.find(m => m.id === id)
}

const patternRegex = (p) => new RegExp('^' + p.replace(/:[^/]+/g, '[^/]+') + '$')

/** True when `pathname` is exactly a module path, a detail route of one, or a legacy redirect source. */
export function isKnownPath(pathname) {
  const clean = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
  if (REDIRECTS.some(r => r.from === clean)) return true
  return MODULES.some(m => [m.path, ...m.paths].some(p => patternRegex(p).test(clean)))
}

/** Module owning `pathname`: exact path or detail route first, else longest parent path. */
export function moduleForPath(pathname) {
  const clean = pathname.length > 1 ? pathname.replace(/\/+$/, '') : pathname
  for (const m of MODULES) {
    if ([m.path, ...m.paths].some(p => patternRegex(p).test(clean))) return m
  }
  return MODULES
    .filter(m => m.path !== '/' && clean.startsWith(m.path + '/'))
    .sort((a, b) => b.path.length - a.path.length)[0] || null
}

/** Command palette entries, in display order. */
export function paletteCommands() {
  const entries = []
  for (const m of MODULES) {
    const p = m.palette
    if (!p) continue
    const icon = p.icon || m.icon
    entries.push({ rank: p.rank, id: p.id || m.id, labelKey: p.labelKey, icon, path: m.path, categoryKey: p.category, ...(p.pro && { pro: true }) })
  }
  for (const r of REDIRECTS) {
    const p = r.palette
    if (!p) continue
    const icon = p.icon
    entries.push({ rank: p.rank, id: p.id, labelKey: p.labelKey, icon, path: p.path, categoryKey: p.category, ...(p.pro && { pro: true }) })
  }
  entries.sort((a, b) => a.rank - b.rank)
  const actions = PALETTE_ACTIONS.map(a => {
    const m = moduleById(a.moduleId)
    const icon = m.icon
    return { id: a.id, labelKey: a.labelKey, icon, path: m.path, action: a.action, categoryKey: ACTION_CATEGORY }
  })
  return [...entries.map(({ rank: _rank, ...e }) => e), ...actions]
}
