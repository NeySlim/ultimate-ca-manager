/**
 * ExportDropdown Component
 * Dropdown button for exporting in multiple formats (PEM/DER/PKCS12)
 */
import { Export, FilePdf } from '@phosphor-icons/react'
import { Dropdown } from './Dropdown'

export function ExportDropdown({ onExport, disabled = false, formats = ['pem', 'der', 'pkcs12'] }) {
  const formatLabels = {
    pem: 'Export as PEM',
    der: 'Export as DER',
    pkcs12: 'Export as PKCS#12',
    p7b: 'Export as P7B',
    crt: 'Export as CRT'
  }

  const formatIcons = {
    pem: <FilePdf size={16} />,
    der: <FilePdf size={16} />,
    pkcs12: <FilePdf size={16} />,
    p7b: <FilePdf size={16} />,
    crt: <FilePdf size={16} />
  }

  const items = formats.map(format => ({
    label: formatLabels[format] || `Export as ${format.toUpperCase()}`,
    icon: formatIcons[format] || <Export size={16} />,
    onClick: () => onExport(format)
  }))

  return (
    <Dropdown
      trigger={
        <div className="flex items-center gap-1.5">
          <Export size={16} />
          Export
        </div>
      }
      items={items}
      disabled={disabled}
    />
  )
}
