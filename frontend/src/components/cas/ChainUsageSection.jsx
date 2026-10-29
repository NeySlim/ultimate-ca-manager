/**
 * ChainUsageSection — what still chains to a CA in what UCM issues and delivers (#400),
 * to tell when an old root can be retired.
 */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Badge } from '../Badge'
import { CompactSection } from '../DetailCard'
import { casService } from '../../services'
import { extractData, formatDate } from '../../lib/utils'

function CertList({ section, t }) {
  return (
    <ul className="space-y-1">
      {section.items.map(item => (
        <li key={item.id} className="text-2xs flex flex-wrap gap-x-2">
          <Link to={`/certificates/${item.id}`} className="text-accent-primary hover:underline">
            {item.name || item.cn}
          </Link>
          <span className="text-text-tertiary">{item.ca}</span>
          <span className="text-text-tertiary">{t('chainUsage.expires', { date: formatDate(item.valid_to) })}</span>
        </li>
      ))}
    </ul>
  )
}

function Block({ title, section, t, children }) {
  return (
    <div className="space-y-1" data-testid="chain-usage-block">
      <div className="flex items-center gap-2">
        <span className="text-xs font-medium text-text-primary">{title}</span>
        <Badge variant={section.count ? 'warning' : 'success'} size="sm">{section.count}</Badge>
      </div>
      {children}
      {section.truncated && (
        <p className="text-2xs text-text-tertiary">{t('chainUsage.truncated', { count: section.items.length })}</p>
      )}
    </div>
  )
}

export function ChainUsageSection({ ca }) {
  const { t } = useTranslation()
  const [usage, setUsage] = useState(null)
  const [state, setState] = useState('idle')
  const [opened, setOpened] = useState(false)
  const loadedFor = useRef(null)
  const id = ca?.id
  const pending = ca?.pending

  useEffect(() => {
    loadedFor.current = null
    setUsage(null)
    setState('idle')
    if (!id || pending) setOpened(false)
  }, [id, pending])

  // The scan walks every chain of the installation: only ask once the section is opened, again after
  // a failure or a change of CA, and never keep the answer of a CA that is no longer shown.
  useEffect(() => {
    if (!opened || !id || pending || loadedFor.current === id) return undefined
    let stale = false
    setState('loading')
    casService.getChainUsage(id)
      .then(res => { if (!stale) { loadedFor.current = id; setUsage(extractData(res)); setState('done') } })
      .catch(() => { if (!stale) setState('error') })
    return () => { stale = true }
  }, [opened, id, pending])

  if (!id || pending) return null
  const { issued, via_cross: viaCross, deployments, subordinate_cas: subordinate, crl_deployments: crl } = usage || {}
  const offered = viaCross?.cross_certificates?.filter(x => x.servable) || []
  const idle = usage && !issued.count && !viaCross.count && !deployments.count && !subordinate?.count && !crl?.count

  return (
    <CompactSection title={t('chainUsage.title')} collapsible defaultOpen={false} onToggle={setOpened}>
      <div className="space-y-3" data-testid="chain-usage">
        {state === 'loading' && <p className="text-xs text-text-secondary">{t('common.loading')}</p>}
        {state === 'error' && <p className="text-xs text-status-danger" data-testid="chain-usage-error">{t('chainUsage.error')}</p>}
        {usage && idle && !offered.length && (
          <p className="text-xs text-status-success" data-testid="chain-usage-empty">{t('chainUsage.empty')}</p>
        )}
        {usage && idle && offered.length > 0 && (
          <p className="text-xs text-status-warning" data-testid="chain-usage-offered">{t('chainUsage.offered', { count: offered.length })}</p>
        )}
        {usage && (
          <>
            <Block title={t('chainUsage.issued')} section={issued} t={t}>
              <CertList section={issued} t={t} />
            </Block>
            <Block title={t('chainUsage.viaCross')} section={viaCross} t={t}>
              <CertList section={viaCross} t={t} />
              {viaCross.cross_certificates?.map(x => (
                <p key={x.id} className="text-2xs text-text-tertiary">
                  {t('chainUsage.crossRow', { id: x.id, ca: x.ca_name })}
                  {' - '}{x.served ? t('crossCerts.served') : t('chainUsage.notServed')}
                  {!x.servable && ` - ${t('chainUsage.notServable')}`}
                </p>
              ))}
            </Block>
            {subordinate && (
              <Block title={t('chainUsage.subordinate')} section={subordinate} t={t}>
                <ul className="space-y-1">
                  {subordinate.items.map(item => (
                    <li key={item.id} className="text-2xs flex flex-wrap gap-x-2">
                      <span className="text-text-primary">{item.name}</span>
                      <span className="text-text-tertiary">{t('chainUsage.expires', { date: formatDate(item.valid_to) })}</span>
                    </li>
                  ))}
                </ul>
              </Block>
            )}
            <Block title={t('chainUsage.deployments')} section={deployments} t={t}>
              <ul className="space-y-1">
                {deployments.items.map(item => (
                  <li key={item.id} className="text-2xs flex flex-wrap gap-x-2">
                    <span className="text-text-primary">{item.target}</span>
                    <Link to={`/certificates/${item.certificate_id}`} className="text-accent-primary hover:underline">
                      {item.certificate}
                    </Link>
                    <span className="text-text-tertiary">{item.variant}</span>
                  </li>
                ))}
              </ul>
            </Block>
            {crl && (
              <Block title={t('chainUsage.crlDeployments')} section={crl} t={t}>
                <ul className="space-y-1">
                  {crl.items.map(item => (
                    <li key={item.id} className="text-2xs flex flex-wrap gap-x-2">
                      <span className="text-text-primary">{item.target}</span>
                      <span className="text-text-tertiary">{item.ca_name}</span>
                      <span className="text-text-tertiary">{item.crl_path}</span>
                    </li>
                  ))}
                </ul>
              </Block>
            )}
            <p className="text-2xs text-text-tertiary">{t('chainUsage.note')}</p>
          </>
        )}
      </div>
    </CompactSection>
  )
}
