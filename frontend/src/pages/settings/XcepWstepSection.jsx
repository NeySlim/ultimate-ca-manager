import { useState, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { WindowsLogo } from '@phosphor-icons/react'
import { DetailHeader, DetailSection, DetailContent, Modal } from '../../components'
import { casService } from '../../services'
import WindowsSettingsPanel from './WindowsSettingsPanel'
import WindowsProfileList from './WindowsProfileList'
import WindowsProfileEditor from './WindowsProfileEditor'

/** Windows autoenrollment: the shared switches, then the enrollment profiles, one per realm. */
export default function XcepWstepSection({ hasPermission }) {
  const { t } = useTranslation()
  const [cas, setCas] = useState([])
  const [editing, setEditing] = useState(null) // a profile row, or {} for a new one
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    casService.getAll()
      .then(response => { if (!cancelled) setCas(response.data || []) })
      .catch(() => {})
    return () => { cancelled = true }
  }, [])

  const canWrite = hasPermission('write:xcep')
  const canUploadKeytab = canWrite && hasPermission('write:kerberos')

  return (
    <DetailContent>
      <DetailHeader
        icon={WindowsLogo}
        title={t('xcepWstep.title')}
        subtitle={t('xcepWstep.subtitle')}
      />

      <WindowsSettingsPanel hasPermission={hasPermission} />

      <DetailSection title={t('xcepWstep.profilesTitle')} icon={WindowsLogo} iconClass="icon-bg-cyan">
        <p className="text-xs text-text-secondary mb-3">{t('xcepWstep.profilesDescription')}</p>
        <WindowsProfileList
          cas={cas}
          canWrite={canWrite}
          reloadKey={reloadKey}
          onEdit={setEditing}
          onCreate={() => setEditing({})}
        />
      </DetailSection>

      <Modal
        open={Boolean(editing)}
        onClose={() => setEditing(null)}
        title={editing?.id ? t('xcepWstep.editProfile', { name: editing.name }) : t('xcepWstep.addProfile')}
        size="lg"
      >
        {editing && (
          <WindowsProfileEditor
            key={editing.id || 'new'}
            profile={editing.id ? editing : null}
            cas={cas}
            canWrite={canWrite}
            canUploadKeytab={canUploadKeytab}
            onCancel={() => setEditing(null)}
            onSaved={() => { setEditing(null); setReloadKey(k => k + 1) }}
          />
        )}
      </Modal>
    </DetailContent>
  )
}
