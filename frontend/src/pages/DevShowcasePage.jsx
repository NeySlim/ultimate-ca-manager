/**
 * Dev Component Showcase Page
 * Displays all UI components with their variants for design/theme testing.
 * Only available in development mode (import.meta.env.DEV).
 */
import { useState } from 'react'
import {
  Palette, PaintBrush, Cube, Stack, Cards, ToggleLeft, TextT,
  CheckSquare, Warning, Info, ShieldCheck, Lightning, Gear,
  Certificate, Lock, Key, User, Users, Eye, EyeSlash,
  ArrowRight, Plus, Trash, PencilSimple, MagnifyingGlass,
  Download, Upload, Copy, Check, X, CaretDown, CaretRight,
  Fingerprint, Globe, Clock, CalendarBlank, Tag, Folder,
  Star, Heart, Bell, ChatCircle, ChartBar, Database
} from '@phosphor-icons/react'
import {
  Button, Badge, Card, Input, Textarea, Select, DatePicker,
  Modal, FormModal, ConfirmModal, Dropdown, FileUpload,
  Tabs, Tooltip, HelpTooltip, HelpCard, SearchBar,
  StatusIndicator, LoadingSpinner, EmptyState, Pagination,
  IconBadge, IconAvatar, ExportActions,
  DetailHeader, DetailSection, DetailGrid, DetailField, DetailContent, DetailTabs,
  CompactSection, CompactGrid, CompactField, CompactStats, CompactActions, CompactHeader,
  RichStatsBar, KeyIndicator, TreeView,
  FilterSelect, ResponsiveLayout
} from '../components'
import { ToggleSwitch } from '../components/ui/ToggleSwitch'

export default function DevShowcasePage() {
  const [activeSection, setActiveSection] = useState('buttons')
  const [modalOpen, setModalOpen] = useState(false)
  const [formModalOpen, setFormModalOpen] = useState(false)
  const [confirmModalOpen, setConfirmModalOpen] = useState(false)
  const [inputValue, setInputValue] = useState('')
  const [selectValue, setSelectValue] = useState('')
  const [toggleValue, setToggleValue] = useState(false)
  const [searchValue, setSearchValue] = useState('')
  const [currentPage, setCurrentPage] = useState(1)
  const [dateValue, setDateValue] = useState('')
  const [textareaValue, setTextareaValue] = useState('')

  const sections = [
    { id: 'buttons', label: 'Buttons', icon: Cube },
    { id: 'badges', label: 'Badges & Status', icon: Tag },
    { id: 'iconbadges', label: 'IconBadge & Avatar', icon: Fingerprint },
    { id: 'cards', label: 'Cards', icon: Cards },
    { id: 'inputs', label: 'Form Inputs', icon: TextT },
    { id: 'selects', label: 'Selects & Toggles', icon: ToggleLeft },
    { id: 'modals', label: 'Modals & Dialogs', icon: Stack },
    { id: 'detail', label: 'Detail Components', icon: Eye },
    { id: 'compact', label: 'Compact Detail', icon: CheckSquare },
    { id: 'feedback', label: 'Feedback & Status', icon: Info },
    { id: 'navigation', label: 'Navigation & Data', icon: MagnifyingGlass },
    { id: 'misc', label: 'Misc Components', icon: Palette },
  ]

  return (
    <ResponsiveLayout
      icon={PaintBrush}
      title="Component Showcase"
      subtitle="All UI components with variants — dev only"
    >
      {/* Section Navigation */}
      <div className="flex flex-wrap gap-2 mb-6">
        {sections.map(s => (
          <Button
            key={s.id}
            variant={activeSection === s.id ? 'primary' : 'ghost'}
            size="sm"
            onClick={() => setActiveSection(s.id)}
          >
            <s.icon size={14} />
            {s.label}
          </Button>
        ))}
      </div>

      {/* ═══════════ BUTTONS ═══════════ */}
      {activeSection === 'buttons' && (
        <div className="space-y-6">
          <SectionTitle title="Button Variants" />
          <div className="flex flex-wrap gap-3">
            <Button variant="primary">Primary</Button>
            <Button variant="secondary">Secondary</Button>
            <Button variant="danger">Danger</Button>
            <Button variant="danger-soft">Danger Soft</Button>
            <Button variant="warning-soft">Warning Soft</Button>
            <Button variant="success">Success</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="outline">Outline</Button>
          </div>

          <SectionTitle title="Button Sizes" />
          <div className="flex flex-wrap items-center gap-3">
            <Button variant="primary" size="xs">Extra Small</Button>
            <Button variant="primary" size="sm">Small</Button>
            <Button variant="primary">Default</Button>
            <Button variant="primary" size="lg">Large</Button>
          </div>

          <SectionTitle title="Button States" />
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" disabled>Disabled</Button>
            <Button variant="primary" loading loadingText="Saving...">Loading</Button>
            <Button variant="secondary" loading>Loading</Button>
            <Button variant="danger" disabled>Disabled Danger</Button>
          </div>

          <SectionTitle title="Buttons with Icons" />
          <div className="flex flex-wrap gap-3">
            <Button variant="primary"><Plus size={16} /> Create</Button>
            <Button variant="danger"><Trash size={16} /> Delete</Button>
            <Button variant="secondary"><Download size={16} /> Export</Button>
            <Button variant="ghost"><PencilSimple size={16} /> Edit</Button>
            <Button variant="success"><Check size={16} /> Approve</Button>
            <Button variant="outline"><Upload size={16} /> Upload</Button>
          </div>
        </div>
      )}

      {/* ═══════════ BADGES & STATUS ═══════════ */}
      {activeSection === 'badges' && (
        <div className="space-y-6">
          <SectionTitle title="Badge Variants" />
          <div className="flex flex-wrap gap-2">
            {['default', 'primary', 'secondary', 'success', 'warning', 'danger', 'info',
              'outline', 'emerald', 'red', 'blue', 'yellow', 'purple', 'violet',
              'amber', 'orange', 'cyan', 'teal', 'gray'].map(v => (
              <Badge key={v} variant={v}>{v}</Badge>
            ))}
          </div>

          <SectionTitle title="Badge Sizes" />
          <div className="flex flex-wrap items-center gap-2">
            <Badge variant="primary" size="sm">Small</Badge>
            <Badge variant="primary">Default</Badge>
            <Badge variant="primary" size="lg">Large</Badge>
          </div>

          <SectionTitle title="Badge with Dot & Pulse" />
          <div className="flex flex-wrap gap-2">
            <Badge variant="success" dot>Active</Badge>
            <Badge variant="danger" dot pulse>Critical</Badge>
            <Badge variant="warning" dot>Warning</Badge>
            <Badge variant="info" dot>Info</Badge>
          </div>

          <SectionTitle title="Badge with Icons" />
          <div className="flex flex-wrap gap-2">
            <Badge variant="success" icon={ShieldCheck}>Verified</Badge>
            <Badge variant="danger" icon={Warning}>Expired</Badge>
            <Badge variant="info" icon={Certificate}>Certificate</Badge>
            <Badge variant="purple" icon={Key}>Private Key</Badge>
          </div>

          <SectionTitle title="StatusIndicator" />
          <div className="flex flex-wrap items-center gap-4">
            {['valid', 'success', 'expiring', 'warning', 'expired', 'danger',
              'error', 'revoked', 'pending', 'active', 'inactive', 'disabled',
              'online', 'offline'].map(s => (
              <div key={s} className="flex items-center gap-2">
                <StatusIndicator status={s} />
                <span className="text-sm text-[var(--color-text-secondary)]">{s}</span>
              </div>
            ))}
          </div>

          <SectionTitle title="StatusIndicator Sizes" />
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-2">
              <StatusIndicator status="success" size="sm" /> <span className="text-sm">sm</span>
            </div>
            <div className="flex items-center gap-2">
              <StatusIndicator status="success" size="md" /> <span className="text-sm">md</span>
            </div>
            <div className="flex items-center gap-2">
              <StatusIndicator status="success" size="lg" /> <span className="text-sm">lg</span>
            </div>
            <div className="flex items-center gap-2">
              <StatusIndicator status="danger" size="lg" pulse /> <span className="text-sm">lg + pulse</span>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════ ICON BADGES & AVATARS ═══════════ */}
      {activeSection === 'iconbadges' && (
        <div className="space-y-6">
          <SectionTitle title="IconBadge Colors" />
          <div className="flex flex-wrap gap-3">
            {['blue', 'violet', 'purple', 'emerald', 'green', 'teal', 'orange',
              'amber', 'yellow', 'primary', 'success', 'warning', 'danger', 'slate', 'neutral', 'muted'].map(c => (
              <div key={c} className="flex flex-col items-center gap-1">
                <IconBadge icon={Certificate} color={c} size="md" />
                <span className="text-xs text-[var(--color-text-muted)]">{c}</span>
              </div>
            ))}
          </div>

          <SectionTitle title="IconBadge Sizes" />
          <div className="flex flex-wrap items-end gap-3">
            {['table', 'xs', 'sm', 'md', 'lg', 'xl'].map(s => (
              <div key={s} className="flex flex-col items-center gap-1">
                <IconBadge icon={Lock} color="blue" size={s} />
                <span className="text-xs text-[var(--color-text-muted)]">{s}</span>
              </div>
            ))}
          </div>

          <SectionTitle title="IconAvatar" />
          <div className="flex flex-wrap items-end gap-3">
            <IconAvatar icon={User} color="blue" size="sm" />
            <IconAvatar icon={Users} color="emerald" size="md" />
            <IconAvatar icon={ShieldCheck} color="violet" size="lg" />
            <IconAvatar icon={Gear} color="orange" size="xl" />
          </div>

          <SectionTitle title="KeyIndicator" />
          <div className="flex flex-wrap items-center gap-6">
            <div className="flex items-center gap-2">
              <KeyIndicator hasKey={true} /> <span className="text-sm">Has key</span>
            </div>
            <div className="flex items-center gap-2">
              <KeyIndicator hasKey={false} /> <span className="text-sm">No key</span>
            </div>
          </div>
        </div>
      )}

      {/* ═══════════ CARDS ═══════════ */}
      {activeSection === 'cards' && (
        <div className="space-y-6">
          <SectionTitle title="Card Variants" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {['default', 'elevated', 'bordered', 'soft'].map(v => (
              <Card key={v} variant={v}>
                <Card.Header>
                  <h3 className="font-semibold text-[var(--color-text-primary)]">Card — {v}</h3>
                </Card.Header>
                <Card.Body>
                  <p className="text-sm text-[var(--color-text-secondary)]">
                    This is a {v} card variant with header, body, and footer.
                  </p>
                </Card.Body>
                <Card.Footer>
                  <Button variant="ghost" size="sm">Action</Button>
                </Card.Footer>
              </Card>
            ))}
          </div>

          <SectionTitle title="Card Accents" />
          <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
            {['primary', 'success', 'warning', 'danger', 'info', 'purple'].map(a => (
              <Card key={a} accent={a}>
                <Card.Body>
                  <p className="text-sm font-medium text-[var(--color-text-primary)]">Accent: {a}</p>
                </Card.Body>
              </Card>
            ))}
          </div>

          <SectionTitle title="HelpCard Variants" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {['info', 'tip', 'warning', 'help', 'success'].map(v => (
              <HelpCard key={v} variant={v} title={`${v.charAt(0).toUpperCase() + v.slice(1)} Card`}
                items={['First helpful item', 'Second helpful item']} />
            ))}
          </div>
        </div>
      )}

      {/* ═══════════ FORM INPUTS ═══════════ */}
      {activeSection === 'inputs' && (
        <div className="space-y-6">
          <SectionTitle title="Input States" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-3xl">
            <Input label="Default Input" placeholder="Type something..." value={inputValue} onChange={e => setInputValue(e.target.value)} />
            <Input label="With Icon" placeholder="Search..." icon={MagnifyingGlass} value="" onChange={() => {}} />
            <Input label="With Error" placeholder="Invalid..." error="This field is required" value="" onChange={() => {}} />
            <Input label="With Helper" placeholder="Optional..." helperText="This field is optional" value="" onChange={() => {}} />
            <Input label="Disabled" placeholder="Cannot edit" disabled value="" onChange={() => {}} />
            <Input label="Required Field" placeholder="Must fill..." required value="" onChange={() => {}} />
            <Input label="Password" type="password" placeholder="Enter password" showStrength value="" onChange={() => {}} />
            <Input label="Monospace" placeholder="0x1234ABCD" value="" onChange={() => {}} style={{ fontFamily: 'monospace' }} />
          </div>

          <SectionTitle title="Textarea" />
          <div className="max-w-xl">
            <Textarea
              label="Description"
              placeholder="Enter a description..."
              value={textareaValue}
              onChange={e => setTextareaValue(e.target.value)}
              maxLength={500}
              showCount
              helperText="Supports multiline text"
            />
          </div>

          <SectionTitle title="DatePicker" />
          <div className="max-w-xs">
            <DatePicker label="Expiry Date" value={dateValue} onChange={e => setDateValue(e.target.value)} />
          </div>

          <SectionTitle title="FileUpload" />
          <div className="max-w-xl">
            <FileUpload
              label="Upload Certificate"
              accept=".pem,.crt,.cer,.der,.p12,.pfx"
              helperText="PEM, DER, PKCS12 formats accepted (max 10MB)"
              onFileSelect={() => {}}
            />
          </div>
        </div>
      )}

      {/* ═══════════ SELECTS & TOGGLES ═══════════ */}
      {activeSection === 'selects' && (
        <div className="space-y-6">
          <SectionTitle title="Select Component" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4 max-w-3xl">
            <Select
              label="Key Algorithm"
              value={selectValue}
              onChange={e => setSelectValue(e.target.value)}
              options={[
                { value: '', label: 'Select...' },
                { value: 'rsa2048', label: 'RSA 2048' },
                { value: 'rsa4096', label: 'RSA 4096' },
                { value: 'ec256', label: 'EC P-256' },
                { value: 'ec384', label: 'EC P-384' },
              ]}
            />
            <Select
              label="Disabled Select"
              disabled
              value="rsa2048"
              onChange={() => {}}
              options={[{ value: 'rsa2048', label: 'RSA 2048' }]}
            />
          </div>

          <SectionTitle title="FilterSelect" />
          <div className="max-w-xs">
            <FilterSelect
              value=""
              onChange={() => {}}
              options={[
                { value: '', label: 'All Status' },
                { value: 'valid', label: 'Valid' },
                { value: 'expiring', label: 'Expiring' },
                { value: 'expired', label: 'Expired' },
              ]}
            />
          </div>

          <SectionTitle title="ToggleSwitch" />
          <div className="space-y-4 max-w-md">
            <ToggleSwitch
              checked={toggleValue}
              onChange={setToggleValue}
              label="Enable notifications"
              description="Receive email alerts for expiring certificates"
            />
            <ToggleSwitch checked={true} onChange={() => {}} label="Always on" size="sm" />
            <ToggleSwitch checked={false} onChange={() => {}} label="Disabled toggle" disabled />
            <ToggleSwitch checked={true} onChange={() => {}} label="Large toggle" size="lg" />
          </div>

          <SectionTitle title="Dropdown" />
          <div className="flex gap-3">
            <Dropdown
              trigger={<Button variant="secondary">Actions <CaretDown size={14} /></Button>}
              items={[
                { label: 'Edit', icon: PencilSimple, onClick: () => {} },
                { label: 'Duplicate', icon: Copy, onClick: () => {} },
                { label: 'Export', icon: Download, onClick: () => {} },
                { type: 'divider' },
                { label: 'Delete', icon: Trash, onClick: () => {}, variant: 'danger' },
              ]}
            />
            <ExportActions onExport={() => {}} hasPrivateKey={true} variant="secondary" size="sm" />
          </div>
        </div>
      )}

      {/* ═══════════ MODALS ═══════════ */}
      {activeSection === 'modals' && (
        <div className="space-y-6">
          <SectionTitle title="Modal Types" />
          <div className="flex flex-wrap gap-3">
            <Button variant="primary" onClick={() => setModalOpen(true)}>Open Modal</Button>
            <Button variant="secondary" onClick={() => setFormModalOpen(true)}>Open Form Modal</Button>
            <Button variant="danger" onClick={() => setConfirmModalOpen(true)}>Open Confirm</Button>
          </div>

          <Modal open={modalOpen} onClose={() => setModalOpen(false)} title="Basic Modal">
            <div className="p-4">
              <p className="text-[var(--color-text-secondary)]">
                This is a basic modal with a title and close button.
                You can put any content here.
              </p>
              <div className="mt-4 flex justify-end">
                <Button variant="primary" onClick={() => setModalOpen(false)}>Close</Button>
              </div>
            </div>
          </Modal>

          <FormModal
            open={formModalOpen}
            onClose={() => setFormModalOpen(false)}
            title="Create Certificate"
            onSubmit={() => { setFormModalOpen(false) }}
            submitLabel="Create"
          >
            <Input name="commonName" label="Common Name" placeholder="example.com" required value="" onChange={() => {}} />
            <Select
              name="algorithm"
              label="Algorithm"
              value=""
              onChange={() => {}}
              options={[
                { value: 'rsa2048', label: 'RSA 2048' },
                { value: 'ec256', label: 'EC P-256' },
              ]}
            />
            <Input name="days" label="Validity (days)" type="number" placeholder="365" value="" onChange={() => {}} />
          </FormModal>

          <ConfirmModal
            open={confirmModalOpen}
            onClose={() => setConfirmModalOpen(false)}
            onConfirm={() => setConfirmModalOpen(false)}
            title="Delete Certificate"
            message="Are you sure you want to delete this certificate? This action cannot be undone."
            confirmLabel="Delete"
            variant="danger"
          />

          <SectionTitle title="Tooltip & HelpTooltip" />
          <div className="flex flex-wrap items-center gap-6">
            <Tooltip content="This is a tooltip">
              <Button variant="ghost">Hover me (top)</Button>
            </Tooltip>
            <Tooltip content="Bottom tooltip" side="bottom">
              <Button variant="ghost">Hover (bottom)</Button>
            </Tooltip>
            <Tooltip content="Left tooltip" side="left">
              <Button variant="ghost">Hover (left)</Button>
            </Tooltip>
            <span className="flex items-center gap-1 text-sm text-[var(--color-text-secondary)]">
              With help icon <HelpTooltip content="This explains the feature in detail" />
            </span>
          </div>
        </div>
      )}

      {/* ═══════════ DETAIL COMPONENTS ═══════════ */}
      {activeSection === 'detail' && (
        <div className="space-y-6">
          <SectionTitle title="DetailHeader" />
          <div className="border border-[var(--color-border)] rounded-lg overflow-hidden">
            <DetailHeader
              icon={Certificate}
              title="example.com"
              subtitle="Issued by Let's Encrypt R3"
              badge={<Badge variant="success" dot>Valid</Badge>}
              stats={[
                { label: 'Serial', value: '03:A1:B2:C3:D4' },
                { label: 'Expires', value: '2026-12-31' },
              ]}
              actions={
                <div className="flex gap-2">
                  <Button variant="ghost" size="xs"><Download size={14} /></Button>
                  <Button variant="ghost" size="xs"><PencilSimple size={14} /></Button>
                </div>
              }
            />
          </div>

          <SectionTitle title="DetailSection + DetailGrid + DetailField" />
          <div className="border border-[var(--color-border)] rounded-lg p-4 space-y-4 bg-[var(--color-bg-primary)]">
            <DetailSection title="Subject Information" icon={User}>
              <DetailGrid columns={2}>
                <DetailField label="Common Name" value="example.com" copyable />
                <DetailField label="Organization" value="Example Inc." />
                <DetailField label="Country" value="US" />
                <DetailField label="Key Algorithm" value="RSA 2048" mono />
              </DetailGrid>
            </DetailSection>

            <DetailSection title="Validity" icon={Clock}>
              <DetailGrid columns={2}>
                <DetailField label="Not Before" value="2025-01-01 00:00:00 UTC" />
                <DetailField label="Not After" value="2026-12-31 23:59:59 UTC" />
              </DetailGrid>
            </DetailSection>

            <DetailSection title="Extensions" icon={Gear}>
              <DetailContent>
                <div className="text-sm text-[var(--color-text-secondary)] space-y-1">
                  <p>Key Usage: Digital Signature, Key Encipherment</p>
                  <p>Extended Key Usage: TLS Web Server Authentication</p>
                  <p>Subject Alternative Names: example.com, www.example.com</p>
                </div>
              </DetailContent>
            </DetailSection>
          </div>

          <SectionTitle title="DetailTabs" />
          <div className="border border-[var(--color-border)] rounded-lg p-4 bg-[var(--color-bg-primary)]">
            <DetailTabs
              tabs={[
                { id: 'info', label: 'Information' },
                { id: 'chain', label: 'Chain' },
                { id: 'raw', label: 'Raw' },
              ]}
              activeTab="info"
              onChange={() => {}}
            />
          </div>
        </div>
      )}

      {/* ═══════════ COMPACT DETAIL ═══════════ */}
      {activeSection === 'compact' && (
        <div className="space-y-6">
          <SectionTitle title="CompactHeader" />
          <div className="border border-[var(--color-border)] rounded-lg overflow-hidden bg-[var(--color-bg-primary)]">
            <CompactHeader
              icon={Lock}
              title="Internal Root CA"
              subtitle="RSA 4096 — Self-signed"
              badge={<Badge variant="success" size="sm" dot>Active</Badge>}
              iconClass="text-violet-500"
            />
          </div>

          <SectionTitle title="CompactStats" />
          <div className="border border-[var(--color-border)] rounded-lg overflow-hidden bg-[var(--color-bg-primary)] p-3">
            <CompactStats stats={[
              { label: 'Certificates', value: '42', icon: Certificate },
              { label: 'Expiring', value: '3', icon: Warning, variant: 'warning' },
              { label: 'Expired', value: '1', icon: X, variant: 'danger' },
            ]} />
          </div>

          <SectionTitle title="CompactSection + CompactGrid + CompactField" />
          <div className="border border-[var(--color-border)] rounded-lg overflow-hidden bg-[var(--color-bg-primary)] p-3 space-y-2">
            <CompactSection title="Certificate Details" icon={Certificate}>
              <CompactGrid cols={2}>
                <CompactField label="Common Name" value="*.example.com" copyable />
                <CompactField label="Serial Number" value="A1:B2:C3:D4:E5:F6" mono />
                <CompactField label="Key Type" value="RSA 2048" />
                <CompactField label="Signature" value="SHA256withRSA" />
              </CompactGrid>
            </CompactSection>

            <CompactSection title="Issuer" icon={ShieldCheck} collapsible>
              <CompactGrid cols={2}>
                <CompactField label="Issuer CN" value="Internal Root CA" />
                <CompactField label="Issuer Org" value="ACME Corp" />
              </CompactGrid>
            </CompactSection>
          </div>

          <SectionTitle title="CompactActions" />
          <div className="border border-[var(--color-border)] rounded-lg overflow-hidden bg-[var(--color-bg-primary)] p-3">
            <CompactActions>
              <Button variant="primary" size="xs"><Download size={14} /> Export</Button>
              <Button variant="ghost" size="xs"><PencilSimple size={14} /> Renew</Button>
              <Button variant="danger-soft" size="xs"><Trash size={14} /> Revoke</Button>
            </CompactActions>
          </div>
        </div>
      )}

      {/* ═══════════ FEEDBACK & STATUS ═══════════ */}
      {activeSection === 'feedback' && (
        <div className="space-y-6">
          <SectionTitle title="LoadingSpinner" />
          <div className="flex flex-wrap items-center gap-8">
            <div className="flex flex-col items-center gap-2">
              <LoadingSpinner size="sm" />
              <span className="text-xs text-[var(--color-text-muted)]">sm</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <LoadingSpinner size="md" />
              <span className="text-xs text-[var(--color-text-muted)]">md</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <LoadingSpinner size="lg" />
              <span className="text-xs text-[var(--color-text-muted)]">lg</span>
            </div>
            <div className="flex flex-col items-center gap-2">
              <LoadingSpinner size="md" message="Loading certificates..." />
              <span className="text-xs text-[var(--color-text-muted)]">with message</span>
            </div>
          </div>

          <SectionTitle title="EmptyState" />
          <div className="border border-[var(--color-border)] rounded-lg p-4 bg-[var(--color-bg-primary)]">
            <EmptyState
              icon={Certificate}
              title="No certificates found"
              description="Create your first certificate or import an existing one."
              action={<Button variant="primary"><Plus size={16} /> Create Certificate</Button>}
            />
          </div>

          <SectionTitle title="RichStatsBar" />
          <RichStatsBar stats={[
            { icon: Certificate, label: 'Total', value: 156, variant: 'default' },
            { icon: Check, label: 'Valid', value: 142, variant: 'success' },
            { icon: Warning, label: 'Expiring', value: 8, variant: 'warning' },
            { icon: X, label: 'Expired', value: 6, variant: 'danger' },
          ]} />

          <SectionTitle title="HelpCard Variants" />
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            <HelpCard variant="info" title="Information" items={['Certificates are stored encrypted', 'Auto-renewal is supported']} />
            <HelpCard variant="tip" title="Pro Tip" items={['Use EC P-384 for better security', 'Enable OCSP stapling']} compact />
            <HelpCard variant="warning" title="Warning" items={['This CA is about to expire', 'Renew before Jan 2027']} />
            <HelpCard variant="success" title="All Good" items={['All certificates valid', 'No issues detected']} />
          </div>
        </div>
      )}

      {/* ═══════════ NAVIGATION & DATA ═══════════ */}
      {activeSection === 'navigation' && (
        <div className="space-y-6">
          <SectionTitle title="SearchBar" />
          <div className="max-w-md">
            <SearchBar
              placeholder="Search certificates..."
              value={searchValue}
              onChange={setSearchValue}
              onClear={() => setSearchValue('')}
            />
          </div>

          <SectionTitle title="Pagination" />
          <Pagination
            total={247}
            page={currentPage}
            perPage={25}
            onChange={setCurrentPage}
            showInfo
            showPerPageSelector
          />

          <SectionTitle title="Tabs" />
          <Tabs tabs={[
            { id: 'overview', label: 'Overview', content: <p className="p-4 text-sm text-[var(--color-text-secondary)]">Overview tab content</p> },
            { id: 'details', label: 'Details', content: <p className="p-4 text-sm text-[var(--color-text-secondary)]">Details tab content</p> },
            { id: 'history', label: 'History', content: <p className="p-4 text-sm text-[var(--color-text-secondary)]">History tab content</p> },
          ]} />

          <SectionTitle title="TreeView" />
          <div className="border border-[var(--color-border)] rounded-lg p-4 bg-[var(--color-bg-primary)] max-w-md">
            <TreeView
              nodes={[
                {
                  id: 'root', label: 'Root CA', icon: <Lock size={16} />,
                  children: [
                    {
                      id: 'inter1', label: 'Intermediate CA 1', icon: <Certificate size={16} />,
                      children: [
                        { id: 'leaf1', label: 'server.example.com', icon: <Globe size={16} /> },
                        { id: 'leaf2', label: 'api.example.com', icon: <Globe size={16} /> },
                      ]
                    },
                    {
                      id: 'inter2', label: 'Intermediate CA 2', icon: <Certificate size={16} />,
                      children: [
                        { id: 'leaf3', label: 'mail.example.com', icon: <Globe size={16} /> },
                      ]
                    },
                  ]
                },
              ]}
              onSelect={() => {}}
            />
          </div>
        </div>
      )}

      {/* ═══════════ MISC COMPONENTS ═══════════ */}
      {activeSection === 'misc' && (
        <div className="space-y-6">
          <SectionTitle title="Color Palette (CSS Variables)" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            {[
              { name: '--color-bg-primary', label: 'bg-primary' },
              { name: '--color-bg-secondary', label: 'bg-secondary' },
              { name: '--color-bg-tertiary', label: 'bg-tertiary' },
              { name: '--color-bg-hover', label: 'bg-hover' },
              { name: '--color-text-primary', label: 'text-primary' },
              { name: '--color-text-secondary', label: 'text-secondary' },
              { name: '--color-text-muted', label: 'text-muted' },
              { name: '--color-border', label: 'border' },
              { name: '--color-accent', label: 'accent' },
              { name: '--color-accent-hover', label: 'accent-hover' },
              { name: '--color-success', label: 'success' },
              { name: '--color-warning', label: 'warning' },
              { name: '--color-danger', label: 'danger' },
              { name: '--color-info', label: 'info' },
              { name: '--sidebar-bg', label: 'sidebar-bg' },
              { name: '--sidebar-text', label: 'sidebar-text' },
            ].map(c => (
              <div key={c.name} className="flex items-center gap-2 p-2 rounded border border-[var(--color-border)]">
                <div
                  className="w-8 h-8 rounded border border-[var(--color-border)]"
                  style={{ backgroundColor: `var(${c.name})` }}
                />
                <span className="text-xs text-[var(--color-text-secondary)] font-mono">{c.label}</span>
              </div>
            ))}
          </div>

          <SectionTitle title="Typography" />
          <div className="space-y-2 bg-[var(--color-bg-primary)] border border-[var(--color-border)] rounded-lg p-4">
            <h1 className="text-2xl font-bold text-[var(--color-text-primary)]">Heading 1 — 2xl bold</h1>
            <h2 className="text-xl font-semibold text-[var(--color-text-primary)]">Heading 2 — xl semibold</h2>
            <h3 className="text-lg font-medium text-[var(--color-text-primary)]">Heading 3 — lg medium</h3>
            <p className="text-base text-[var(--color-text-primary)]">Body text — base</p>
            <p className="text-sm text-[var(--color-text-secondary)]">Secondary text — sm secondary</p>
            <p className="text-xs text-[var(--color-text-muted)]">Muted text — xs muted</p>
            <p className="text-sm font-mono text-[var(--color-text-primary)]">Monospace — for serial numbers, fingerprints</p>
          </div>

          <SectionTitle title="Spacing & Layout Reference" />
          <div className="flex gap-2 items-end">
            {[1, 2, 3, 4, 6, 8, 12, 16].map(s => (
              <div key={s} className="flex flex-col items-center gap-1">
                <div
                  className="bg-[var(--color-accent)] rounded"
                  style={{ width: `${s * 4}px`, height: `${s * 4}px` }}
                />
                <span className="text-[10px] text-[var(--color-text-muted)]">{s * 4}px</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </ResponsiveLayout>
  )
}

function SectionTitle({ title }) {
  return (
    <h3 className="text-sm font-semibold text-[var(--color-text-primary)] uppercase tracking-wider border-b border-[var(--color-border)] pb-2">
      {title}
    </h3>
  )
}
