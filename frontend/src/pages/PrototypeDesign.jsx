/**
 * Design Prototype - Mix Header A + Sections B
 */
import { useState } from 'react'
import { 
  Certificate, ShieldCheck, Clock, CheckCircle, Key, Eye, Download,
  Trash, ArrowsClockwise, User, CalendarBlank, Fingerprint
} from '@phosphor-icons/react'
import { 
  PageLayout, FocusItem, Badge, Button,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailDivider, DetailContent
} from '../components'

// Mock certificate data
const mockCert = {
  name: 'api.example.com',
  subject: 'CN=api.example.com, O=Example Corp, C=US',
  issuer: 'CN=Example Intermediate CA, O=Example Corp',
  serial: 'A1:B2:C3:D4:E5:F6:78:90',
  validFrom: '2025-01-15',
  validTo: '2026-01-15',
  status: 'valid',
  keyType: 'RSA 2048',
  signatureAlgo: 'SHA256-RSA',
  daysRemaining: 350,
  fingerprint: 'A1:B2:C3:D4:E5:F6:78:90:AB:CD:EF:12:34:56:78:90:A1:B2:C3:D4:E5:F6:78:90:AB:CD:EF:12:34:56:78:90'
}

export default function PrototypeDesign() {
  const focusContent = (
    <div className="p-2 space-y-1">
      <FocusItem
        icon={Certificate}
        title="api.example.com"
        subtitle="Expires in 350 days"
        badge={<Badge variant="emerald" size="sm">Valid</Badge>}
        selected={true}
      />
      <FocusItem
        icon={Certificate}
        title="web.example.com"
        subtitle="Expires in 45 days"
        badge={<Badge variant="amber" size="sm">Expiring</Badge>}
      />
      <FocusItem
        icon={Certificate}
        title="mail.example.com"
        subtitle="Expired"
        badge={<Badge variant="red" size="sm">Expired</Badge>}
      />
    </div>
  )

  return (
    <PageLayout
      title="Certificates"
      focusTitle="Certificates"
      focusContent={focusContent}
      focusFooter="3 certificate(s)"
    >
      <DetailContent>
        {/* Header A Style */}
        <DetailHeader
          icon={Certificate}
          title={mockCert.name}
          subtitle={mockCert.subject}
          badge={
            <Badge variant="emerald" size="lg">
              <CheckCircle size={14} weight="fill" />
              Valid
            </Badge>
          }
          stats={[
            { icon: Clock, label: 'Expires in', value: `${mockCert.daysRemaining} days` },
            { icon: Key, label: 'Key:', value: mockCert.keyType },
          ]}
          actions={[
            { label: 'Export', icon: Download, onClick: () => {} },
            { label: 'Renew', icon: ArrowsClockwise, onClick: () => {} },
            { label: 'Delete', icon: Trash, variant: 'danger', onClick: () => {} },
          ]}
        />

        {/* Sections B Style */}
        <DetailSection title="Subject Information">
          <DetailGrid>
            <DetailField label="Common Name" value={mockCert.name} />
            <DetailField label="Organization" value="Example Corp" />
            <DetailField label="Country" value="United States" />
            <DetailField label="Organizational Unit" value="IT Department" />
          </DetailGrid>
        </DetailSection>

        <DetailDivider />

        <DetailSection title="Validity Period">
          <DetailGrid>
            <DetailField label="Not Before" value={mockCert.validFrom} />
            <DetailField label="Not After" value={mockCert.validTo} />
          </DetailGrid>
        </DetailSection>

        <DetailDivider />

        <DetailSection title="Issuer Information">
          <DetailGrid>
            <DetailField label="Issuer CA" value="Example Intermediate CA" />
            <DetailField label="Organization" value="Example Corp" />
          </DetailGrid>
        </DetailSection>

        <DetailDivider />

        <DetailSection title="Technical Details">
          <DetailGrid>
            <DetailField label="Key Algorithm" value={mockCert.keyType} />
            <DetailField label="Signature Algorithm" value={mockCert.signatureAlgo} />
            <DetailField 
              label="Serial Number" 
              value={mockCert.serial} 
              mono 
              copyable 
              fullWidth 
            />
          </DetailGrid>
        </DetailSection>

        <DetailDivider />

        <DetailSection title="Fingerprints">
          <DetailGrid columns={1}>
            <DetailField 
              label="SHA-256" 
              value={mockCert.fingerprint} 
              mono 
              copyable 
              fullWidth 
            />
          </DetailGrid>
        </DetailSection>
      </DetailContent>
    </PageLayout>
  )
}
