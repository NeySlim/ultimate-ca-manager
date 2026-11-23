/**
 * The detached windows drawn over the console, under the zone's scope (.atl) so the inspector's
 * sections keep their look. Each kind brings its body on demand, so the shell does not carry the
 * pages' code. Nothing is drawn on a phone.
 */
import { Suspense, lazy, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { AtlScopeContext } from '../atelier/scope'
import { SkeletonPanel } from '../atelier/Skeleton'
import { DetachedWindow } from './DetachedWindow'
import { useDetached } from './useDetached'
import { KIND_ICONS } from './kindIcons'
import { maxRect, workArea } from './geometry'

// The window's body for each kind, read when the first window of that kind opens; `label`: the type its bar names
export const KINDS = {
  certificate: { icon: KIND_ICONS.certificate, label: 'common.certificate', Body: lazy(() => import('../../pages/certificates/CertificateFloat')) },
  ca: { icon: KIND_ICONS.ca, label: 'common.ca', Body: lazy(() => import('../../pages/cas/CAFloat')) },
  csr: { icon: KIND_ICONS.csr, label: 'common.csr', Body: lazy(() => import('../../pages/csrs/CsrFloat')) },
  compare: { icon: KIND_ICONS.compare, Body: lazy(() => import('../../pages/certificates/compare/CompareFloat')) },
}

const loadSheets = () => Promise.all([
  import('../../styles/atelier/scope.css'), import('../../styles/atelier/maquette.css'), import('../../styles/atelier/extensions.css'),
  import('../../styles/atelier/detached.css'),
])

const BASE_Z = 60

export function DetachedLayer() {
  const { t } = useTranslation()
  const detached = useDetached()
  const any = !!detached?.windows.length
  useEffect(() => { if (any) loadSheets().catch(() => {}) }, [any])
  if (!detached?.available || !any) return null
  const { windows, rects, maxed = {}, focusKey, clearFocus, close, front, place, toggleMax, retitle, replace } = detached
  // Read at each drawing: a browser resize redraws the layer (the provider clamps the rects)
  const full = windows.some((w) => maxed[w.key]) ? maxRect(workArea(), window.innerWidth) : null
  // Drawn in the order they opened, stacked by their rank in front (z)
  const ranks = new Map([...windows].sort((a, b) => (a.z || 0) - (b.z || 0)).map((w, i) => [w.key, i]))
  const top = [...ranks.keys()].at(-1)
  return (
    <div className="atl atl-island detached-layer">
      <AtlScopeContext.Provider value>
        {windows.map((w) => {
          const kind = KINDS[w.kind]
          if (!kind || !rects[w.key]) return null
          const { Body } = kind
          const prefix = `float-${w.key.replace(/[^a-z0-9]/gi, '-')}-`
          const maximized = !!maxed[w.key]
          return (
            <DetachedWindow key={w.key} wkey={w.key} icon={kind.icon} kindLabel={kind.label && t(kind.label)} title={w.title || t('common.loading')} rect={maximized ? full : rects[w.key]}
              maximized={maximized} onToggleMax={() => toggleMax(w.key)}
              z={BASE_Z + ranks.get(w.key)} front={w.key === top} onPlace={(r) => place(w.key, r)} onFront={() => front(w.key)} onClose={() => close(w.key)}
              takeFocus={focusKey === w.key} onFocused={clearFocus}>
              <Suspense fallback={<SkeletonPanel label={t('common.loading')} />}>
                <Body ids={w.ids} idPrefix={prefix} onTitle={(title) => retitle(w.key, title)}
                  onClose={() => close(w.key)} onReplace={(ids) => replace(w.key, ids)} />
              </Suspense>
            </DetachedWindow>
          )
        })}
      </AtlScopeContext.Provider>
    </div>
  )
}

export default DetachedLayer
