/**
 * How a certificate entered UCM: label key and icon per source. Unknown or legacy
 * values still show, humanized, so a filter option never disappears.
 */
import { Globe, UploadSimple, Certificate, Buildings, SealCheck } from '@phosphor-icons/react'
import { RefreshIcon } from '../../components/list/atelierIcons'

export const SOURCE_LABEL_KEYS = {
  manual: 'sourceManual',
  import: 'sourceImport',
  imported: 'sourceImport',
  upload: 'sourceUpload',
  acme: 'sourceAcme',
  acme_client: 'sourceAcmeClient',
  'acme-renewal': 'sourceAcmeRenewal',
  letsencrypt: 'sourceLetsencrypt',
  scep: 'sourceScep',
  est: 'sourceEst',
  msca: 'sourceMsca',
  approval: 'sourceApproval',
  web: 'sourceWeb',
}

const SOURCE_ICONS = {
  import: UploadSimple,
  imported: UploadSimple,
  upload: UploadSimple,
  acme: RefreshIcon,
  acme_client: RefreshIcon,
  'acme-renewal': RefreshIcon,
  letsencrypt: RefreshIcon,
  scep: Globe,
  est: Globe,
  msca: Buildings,
  approval: SealCheck,
}

export const humanizeSource = (s) =>
  String(s).replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase())

/** A row without a source was issued by hand (the stats endpoint says 'manual' too). */
export const sourceOf = (row) => row?.source || 'manual'

export const sourceLabel = (source, t) =>
  (SOURCE_LABEL_KEYS[source] ? t(`certificates.${SOURCE_LABEL_KEYS[source]}`) : humanizeSource(source))

export const sourceIcon = (source) => SOURCE_ICONS[source] || Certificate
