/**
 * Search and navigation (Ctrl K), the mockup's command(): its narrow dialog, a search field, then one
 * flat list of results (records found on the server, favourites, recent items, pages and actions),
 * each with its icon, its name and a hint. Arrows move between the field and the results.
 */
import { useState, useEffect, useRef, useMemo, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { useOpenEntity } from '../hooks/useOpenEntity'
import { useTranslation } from 'react-i18next'
import { AtelierDialog } from './atelier/AtelierDialog'
import { Icon } from './atelier/Icon'
import { useAllRecentHistory, useAllFavorites } from '../hooks'
import { searchService } from '../services'
import { familyOf, glyphOf, moduleById, moduleForPath, paletteCommands, paletteViews } from '../navigation/registry'

// ACME accounts and SCEP profiles found by the search: [result group, hint, page, glyph, family]
const PROTOCOL_OBJECTS = [
  ['acme_accounts', 'commandPalette.acmeAccount', moduleById('acme').path, glyphOf(moduleById('acme')), familyOf(moduleById('acme'))],
  ['scep_profiles', 'commandPalette.scepProfile', moduleById('scep').path, glyphOf(moduleById('scep')), familyOf(moduleById('scep'))],
]
// The module of a record type, whose family tints the record's icon in Aurore
const TYPE_MODULE = { certificates: 'certificates', certificate: 'certificates', cas: 'cas', ca: 'cas', users: 'users', user: 'users', csrs: 'csrs', csr: 'csrs', templates: 'templates', template: 'templates' }
const typeFamily = (type) => familyOf(moduleById(TYPE_MODULE[type]))

/**
 * `can` ({ isAdmin, hasPermission }) keeps the pages and actions the account may open; omitted, all of them.
 * onOpenHelp: the help of the current page, listed with the actions (on a phone the bar hides its button).
 * guideHref: the guide's chapter of the current page, opened in a new tab by the Guide entry.
 */
export function CommandPalette({ open, onOpenChange, can, onOpenHelp, guideHref = '/guide' }) {
  const navigate = useNavigate()
  const openInInspector = useOpenEntity()
  // The control focused before the palette opened, and whether the palette handed over to the inspector
  const returnTo = useRef(null)
  const openedInspector = useRef(false)
  const { t } = useTranslation()
  const [search, setSearch] = useState('')
  const [searchResults, setSearchResults] = useState(null)
  const [isSearching, setIsSearching] = useState(false)
  const inputRef = useRef(null)
  const listRef = useRef(null)
  const searchTimeoutRef = useRef(null)
  const { allRecent, refreshHistory } = useAllRecentHistory()
  const { allFavorites, refreshFavorites } = useAllFavorites()

  // The mockup's icon of a record type
  const getTypeIcon = (type) => {
    switch (type) {
      case 'certificates': case 'certificate': return 'cert'
      case 'cas': case 'ca': return 'shield'
      case 'users': case 'user': return 'users'
      case 'csrs': case 'csr': return 'file'
      case 'templates': case 'template': return 'template'
      default: return 'clock'
    }
  }
  
  // Certificates and CAs open in the dock their zone draws (InspectorContext); the other types go to their page
  const INSPECTOR_TYPE = { certificates: 'certificate', certificate: 'certificate', cas: 'ca', ca: 'ca' }
  const openItem = (type, id) => {
    const inspectorType = INSPECTOR_TYPE[type]
    if (inspectorType) {
      openedInspector.current = true
      openInInspector(inspectorType, id, { origin: returnTo.current })
    }
    else navigate(getTypePath(type, id))
    onOpenChange(false)
  }

  // The page that docks the record, opened on it (`?item=`, the dock's object in the URL)
  const getTypePath = (type, id) => {
    const at = encodeURIComponent(id)
    switch (type) {
      case 'certificates': case 'certificate': return `/certificates?item=${at}`
      case 'cas': case 'ca': return `/cas?authority=${at}`
      case 'users': case 'user': return `/users?item=${at}`
      case 'csrs': case 'csr': return `/csrs?item=${at}`
      case 'templates': case 'template': return `/templates?item=${at}`
      default: return '/'
    }
  }

  // Debounced global search
  const performSearch = useCallback(async (query) => {
    if (!query || query.length < 2) {
      setSearchResults(null)
      setIsSearching(false)
      return
    }
    
    setIsSearching(true)
    try {
      const results = await searchService.globalSearch(query, 5)
      setSearchResults(results)
    } catch {
      setSearchResults(null)
    } finally {
      setIsSearching(false)
    }
  }, [])

  // Debounce search input
  useEffect(() => {
    if (searchTimeoutRef.current) {
      clearTimeout(searchTimeoutRef.current)
    }
    
    if (search.length >= 2) {
      setIsSearching(true)
      searchTimeoutRef.current = setTimeout(() => {
        performSearch(search)
      }, 300)
    } else {
      setSearchResults(null)
      setIsSearching(false)
    }
    
    return () => {
      if (searchTimeoutRef.current) {
        clearTimeout(searchTimeoutRef.current)
      }
    }
  }, [search, performSearch])

  // Refresh history and favorites when opened
  useEffect(() => {
    if (open) {
      refreshHistory()
      refreshFavorites()
    }
  }, [open, refreshHistory, refreshFavorites])

  // The pages and actions the account may open (a few dozen entries, listed again on each render)
  const commands = paletteCommands(can)
  const lower = search.toLowerCase()
  const filteredCommands = !search ? commands : commands.filter(cmd =>
    t(cmd.labelKey).toLowerCase().includes(lower) ||
    t(cmd.categoryKey).toLowerCase().includes(lower)
  )
  // The views of the protocol pages (absent from the mockup): on a search only, matched on « page: view »
  const viewName = (v) => t('commands.viewOf', { page: t(v.pageKey), view: t(v.labelKey) })
  const filteredViews = !search ? [] : paletteViews(can).filter(v => viewName(v).toLowerCase().includes(lower))
  
  // Filter recent items based on search
  const filteredRecent = useMemo(() => {
    if (!allRecent.length) return []
    if (!search) return allRecent.slice(0, 5)
    
    const lower = search.toLowerCase()
    return allRecent.filter(item =>
      item.name?.toLowerCase().includes(lower) ||
      item.subtitle?.toLowerCase().includes(lower) ||
      item.type?.toLowerCase().includes(lower)
    ).slice(0, 5)
  }, [search, allRecent])
  
  // Filter favorites based on search
  const filteredFavorites = useMemo(() => {
    if (!allFavorites.length) return []
    if (!search) return allFavorites.slice(0, 5)
    
    const lower = search.toLowerCase()
    return allFavorites.filter(item =>
      item.name?.toLowerCase().includes(lower) ||
      item.subtitle?.toLowerCase().includes(lower) ||
      item.type?.toLowerCase().includes(lower)
    ).slice(0, 5)
  }, [search, allFavorites])

  // Focus input when opened
  useEffect(() => {
    if (open) {
      setSearch('')
      setTimeout(() => inputRef.current?.focus(), 0)
    }
  }, [open])

  const executeCommand = (command) => {
    onOpenChange(false)
    navigate(command.path)
  }

  // One flat list, in the order of the former sections: records found, favourites, recent items, pages and actions, help
  const SEARCHED = [
    ['certificates', 'certificate', (i) => i.subject || i.status],
    ['cas', 'ca', (i) => i.subject],
    ['users', 'user', (i) => i.email || i.role],
    ['templates', 'template', (i) => i.description],
    ['csrs', 'csr', (i) => i.subject || i.status],
  ]
  const results = [
    ...SEARCHED.flatMap(([key, type, hint]) => (searchResults?.[key] || []).map(item => ({
      key: `${type}-${item.id}`, icon: getTypeIcon(type), family: typeFamily(type), name: item.name, hint: hint(item) || t(`commandPalette.searchSections.${key === 'cas' ? 'certificateAuthorities' : key}`),
      run: () => openItem(type, item.id),
    }))),
    // The mockup's module objects (M:741): named by their type, opened in their page's dock (`?item=`)
    ...PROTOCOL_OBJECTS.flatMap(([key, hint, path, glyph, family]) => (searchResults?.[key] || []).map(item => ({
      key: `${key}-${item.id}`, icon: glyph, family, name: item.name, hint: t(hint),
      run: () => { onOpenChange(false); navigate(`${path}?item=${encodeURIComponent(item.id)}`) },
    }))),
    ...filteredFavorites.map(item => ({
      key: `fav-${item.type}-${item.id}`, icon: getTypeIcon(item.type), family: typeFamily(item.type), name: item.name, hint: item.subtitle || t('commandPalette.favorites'),
      run: () => openItem(item.type, item.id),
    })),
    ...filteredRecent.map(item => ({
      key: `recent-${item.type}-${item.id}`, icon: getTypeIcon(item.type), family: typeFamily(item.type), name: item.name, hint: item.subtitle || t('commandPalette.recent'),
      run: () => openItem(item.type, item.id),
    })),
    ...filteredCommands.map(cmd => ({
      key: `cmd-${cmd.id}`, icon: cmd.action === 'new' || cmd.action === 'upload' ? 'plus' : glyphOf(moduleForPath(cmd.path.split('?')[0])),
      family: familyOf(moduleForPath(cmd.path.split('?')[0])),
      name: t(cmd.labelKey), hint: t(cmd.categoryKey), run: () => executeCommand(cmd),
    })),
    ...filteredViews.map(v => ({
      key: `view-${v.id}`, icon: glyphOf(moduleForPath(v.path.split('?')[0])), family: familyOf(moduleForPath(v.path.split('?')[0])), name: viewName(v), hint: t(v.categoryKey), run: () => executeCommand(v),
    })),
    // The whole guide in a tab of its own (absent from the mockup), on the chapter of the current page
    ...(search && [t('guide.paletteEntry'), t('guide.paletteHint')].some(s => s.toLowerCase().includes(lower)) ? [{
      key: 'guide', icon: 'expand', name: t('guide.paletteEntry'), hint: t('guide.paletteHint'),
      run: () => { onOpenChange(false); window.open(guideHref, '_blank', 'noopener') },
    }] : []),
    // The page's help (absent from the mockup's palette): on a matching search only, after the pages and modules
    ...(onOpenHelp && search && [t('commandPalette.pageHelp'), t('common.help')].some(s => s.toLowerCase().includes(lower)) ? [{
      key: 'page-help', icon: 'help', name: t('commandPalette.pageHelp'), hint: t('common.help'),
      run: () => { onOpenChange(false); onOpenHelp() },
    }] : []),
  ]

  const resultButtons = () => [...(listRef.current?.querySelectorAll('.command-result') || [])]
  // The mockup's keys: the down arrow from the field goes to the first result; arrows move between results,
  // up from the first one back to the field; Enter in the field runs the first result
  const onKeyDown = (e) => {
    const buttons = resultButtons()
    const i = buttons.indexOf(document.activeElement)
    if (e.key === 'ArrowDown') {
      if (!buttons.length) return
      e.preventDefault()
      buttons[Math.min(i + 1, buttons.length - 1)].focus()
    } else if (e.key === 'ArrowUp' && i >= 0) {
      e.preventDefault()
      if (i === 0) inputRef.current?.focus()
      else buttons[i - 1].focus()
    } else if (e.key === 'Enter' && e.target === inputRef.current && results[0]) {
      e.preventDefault()
      results[0].run()
    }
  }

  // The control focused before the palette opened (read before the dialog takes the focus)
  const wasOpen = useRef(false)
  if (open && !wasOpen.current) { returnTo.current = document.activeElement; openedInspector.current = false }
  wasOpen.current = open

  if (!open) return null
  return (
    <AtelierDialog title={t('shell.search')} subtitle={t('commandPalette.subtitle')} size="narrow" testId="command-palette"
      onClose={() => onOpenChange(false)} skipReturn={() => openedInspector.current}>
        <label className="command-search">
          <Icon name="search" />
          <span className="sr-only">{t('commandPalette.searchLabel')}</span>
          <input ref={inputRef} id="command-search" type="search" name="command" autoComplete="off" data-autofocus=""
            placeholder={t('commandPalette.searchPlaceholder')} value={search} onChange={e => setSearch(e.target.value)} onKeyDown={onKeyDown} />
        </label>
        <div className="command-results" id="command-results" ref={listRef} aria-busy={isSearching || undefined} onKeyDown={onKeyDown}>
          {results.map(r => (
            <button key={r.key} type="button" className="command-result" data-family={r.family} onClick={r.run}>
              <Icon name={r.icon} /><span className="name">{r.name}</span>{r.hint && <span className="hint">{r.hint}</span>}
            </button>
          ))}
          {results.length === 0 && !isSearching && (
            <p className="muted" style={{ padding: 16 }}>{t('commandPalette.noCommandsFound')}</p>
          )}
        </div>
    </AtelierDialog>
  )
}

/**
 * Hook to handle global keyboard shortcuts
 */
export function useKeyboardShortcuts({ onCommandPalette }) {
  useEffect(() => {
    const handleKeyDown = (e) => {
      // Cmd+K or Ctrl+K - Open command palette
      if ((e.metaKey || e.ctrlKey) && e.key === 'k') {
        e.preventDefault()
        onCommandPalette?.()
      }
    }

    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [onCommandPalette])
}
