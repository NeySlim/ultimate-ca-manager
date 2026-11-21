/**
 * The root of a zone drawn from the mockup: `.atl` (the scope of the copied rules), then the
 * mockup's #app around the stage, its page content and the inspector dock, as the mockup holds
 * them. #app draws no box of its own here (extensions.css); it carries `dock-right` when the dock
 * is anchored at the right, which the copied rules read.
 */
import { useState } from 'react'
import { DockSideContext } from './dockSide'
import { AtlScopeContext } from './scope'
import { useShellBanners } from '../shell/bannersSlot'
import '../../styles/atelier/scope.css'
import '../../styles/atelier/maquette.css'
import '../../styles/atelier/extensions.css'

/** dock: the inspector, beside the page content; after: what sits after it in the stage (the zone's dialogs). */
export function Zone({ children, dock, after, testId }) {
  const [right, setRight] = useState(false)
  // The shell's state banners (offline, cluster) open the page content, as the mockup's stateBanners()
  const banners = useShellBanners()
  return (
    <div className="atl" data-testid={testId}>
      <AtlScopeContext.Provider value>
        <div id="app" className={right ? 'zone-app dock-right' : 'zone-app'}>
          <main className="stage" id="main">
            <div className="page-content">{banners}{children}</div>
            <DockSideContext.Provider value={setRight}>{dock}</DockSideContext.Provider>
            {after}
          </main>
        </div>
      </AtlScopeContext.Provider>
    </div>
  )
}

export default Zone
