/**
 * ChainUsageSection — what still chains to a CA in what UCM issues and delivers (#400),
 * to tell when an old root can be retired.
 */
import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { Icon } from '../atelier/Icon'
import { SideFold } from './SideField'
import { casService } from '../../services'
import { extractData, formatDate } from '../../lib/utils'

function CertList({ section, t }) {
  return (
    <ul className="link-list">
      {section.items.map(item => (
        <li key={item.id}>
          <Link className="text-link" to={`/certificates/${item.id}`}>{item.name || item.cn}</Link>
          <span className="muted small"> {item.ca} · {t('chainUsage.expires', { date: formatDate(item.valid_to, { time: false }) })}</span>
        </li>
      ))}
    </ul>
  )
}

function Block({ title, section, t, children }) {
  return (
    <>
      <dt data-testid="chain-usage-block">{title}</dt>
      <dd>
        <span className="counter">{section.count}</span>
        {children}
        {section.truncated && <p className="small muted">{t('chainUsage.truncated', { count: section.items.length })}</p>}
      </dd>
    </>
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
    <SideFold id={`chain-usage-${id}`} title={t('chainUsage.title')} onToggle={setOpened} testId="chain-usage">
      {state === 'loading' && <p className="small muted">{t('common.loading')}</p>}
      {state === 'error' && <p className="notice bad" data-testid="chain-usage-error"><Icon name="warning" />{t('chainUsage.error')}</p>}
      {usage && idle && !offered.length && (
        <p className="notice" data-testid="chain-usage-empty"><Icon name="check" />{t('chainUsage.empty')}</p>
      )}
      {usage && idle && offered.length > 0 && (
        <p className="notice warn" data-testid="chain-usage-offered"><Icon name="warning" />{t('chainUsage.offered', { count: offered.length })}</p>
      )}
      {usage && (
        <>
          <dl className="props">
            <Block title={t('chainUsage.issued')} section={issued} t={t}>
              <CertList section={issued} t={t} />
            </Block>
            <Block title={t('chainUsage.viaCross')} section={viaCross} t={t}>
              <CertList section={viaCross} t={t} />
              {viaCross.cross_certificates?.map(x => (
                <p key={x.id} className="small muted">
                  {t('chainUsage.crossRow', { id: x.id, ca: x.ca_name })}
                  {' - '}{x.served ? t('crossCerts.served') : t('chainUsage.notServed')}
                  {!x.servable && ` - ${t('chainUsage.notServable')}`}
                </p>
              ))}
            </Block>
            {subordinate && (
              <Block title={t('chainUsage.subordinate')} section={subordinate} t={t}>
                <ul className="link-list">
                  {subordinate.items.map(item => (
                    <li key={item.id}>{item.name} <span className="muted small">{t('chainUsage.expires', { date: formatDate(item.valid_to, { time: false }) })}</span></li>
                  ))}
                </ul>
              </Block>
            )}
            <Block title={t('chainUsage.deployments')} section={deployments} t={t}>
              <ul className="link-list">
                {deployments.items.map(item => (
                  <li key={item.id}>
                    {item.target} <Link className="text-link" to={`/certificates/${item.certificate_id}`}>{item.certificate}</Link>
                    <span className="muted small"> {item.variant}</span>
                  </li>
                ))}
              </ul>
            </Block>
            {crl && (
              <Block title={t('chainUsage.crlDeployments')} section={crl} t={t}>
                <ul className="link-list">
                  {crl.items.map(item => (
                    <li key={item.id}>{item.target} <span className="muted small">{item.ca_name} {item.crl_path}</span></li>
                  ))}
                </ul>
              </Block>
            )}
          </dl>
          <p className="small muted ca-fold-note">{t('chainUsage.note')}</p>
        </>
      )}
    </SideFold>
  )
}
