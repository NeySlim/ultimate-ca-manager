import { useState, useRef } from 'react';
import {
  FileText,
  Upload,
  UploadSimple,
  Check,
  Warning,
  X,
  FilePlus,
  Certificate,
  Eye,
  Trash,
  Download
} from '@phosphor-icons/react';

// Design System V3
import { Card } from '../../design-system/components/primitives/Card';
import { Button } from '../../design-system/components/primitives/Button';
import { Badge } from '../../design-system/components/primitives/Badge';
import { GradientBadge } from '../../design-system/components/primitives/GradientBadge';
import { GlassCard } from '../../design-system/components/primitives/GlassCard';
import { Stack } from '../../design-system/components/layout/Stack';
import { Inline } from '../../design-system/components/layout/Inline';
import { Grid } from '../../design-system/components/layout/Grid';
import { Modal } from '../../design-system/components/overlays/Modal';
import { Alert } from '../../design-system/components/feedback/Alert';
import { EmptyState } from '../../design-system/components/feedback/EmptyState';
import { Spinner } from '../../design-system/components/feedback/Spinner';

import { useCSRs } from '../../hooks/useCSRs';
import styles from './CSRListV3.module.css';

// Drag & Drop Upload Zone
function UploadZone({ onUpload }) {
  const [isDragging, setIsDragging] = useState(false);
  const [isProcessing, setIsProcessing] = useState(false);
  const fileInputRef = useRef(null);

  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(true);
  };

  const handleDragLeave = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
  };

  const handleDragOver = (e) => {
    e.preventDefault();
    e.stopPropagation();
  };

  const handleDrop = (e) => {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);

    const files = Array.from(e.dataTransfer.files);
    handleFiles(files);
  };

  const handleFileInput = (e) => {
    const files = Array.from(e.target.files);
    handleFiles(files);
  };

  const handleFiles = async (files) => {
    setIsProcessing(true);
    
    // Simulate processing
    await new Promise(resolve => setTimeout(resolve, 1000));
    
    onUpload?.(files);
    setIsProcessing(false);
    
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  return (
    <div
      className={styles.uploadZone}
      data-dragging={isDragging}
      data-processing={isProcessing}
      onDragEnter={handleDragEnter}
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
      onClick={() => fileInputRef.current?.click()}
    >
      <input
        ref={fileInputRef}
        type="file"
        accept=".pem,.csr"
        multiple
        onChange={handleFileInput}
        style={{ display: 'none' }}
      />

      {isProcessing ? (
        <Stack gap="md" align="center">
          <Spinner size="lg" />
          <div className={styles.uploadText}>Processing...</div>
        </Stack>
      ) : (
        <Stack gap="md" align="center">
          <div className={styles.uploadIcon}>
            <UploadSimple size={48} weight="duotone" />
          </div>
          <div>
            <div className={styles.uploadText}>
              Drop CSR files here or click to browse
            </div>
            <div className={styles.uploadSubtext}>
              Supports PEM format (.pem, .csr)
            </div>
          </div>
          <Button variant="primary" leftIcon={<FilePlus size={20} />}>
            Select Files
          </Button>
        </Stack>
      )}
    </div>
  );
}

// CSR Card
function CSRCard({ csr, onView, onIssue, onDelete }) {
  const getStatusIcon = (status) => {
    switch (status) {
      case 'pending': return <Warning size={14} weight="fill" />;
      case 'approved': return <Check size={14} weight="fill" />;
      case 'rejected': return <X size={14} weight="fill" />;
      default: return null;
    }
  };

  const getStatusVariant = (status) => {
    switch (status) {
      case 'pending': return 'warning';
      case 'approved': return 'success';
      case 'rejected': return 'danger';
      default: return 'default';
    }
  };

  return (
    <Card hoverable className={styles.csrCard}>
      <Stack gap="md">
        {/* Header */}
        <Inline gap="md" align="center">
          <div className={styles.csrIcon}>
            <FileText size={24} weight="duotone" />
          </div>
          <div style={{ flex: 1 }}>
            <div className={styles.csrName}>{csr.common_name}</div>
            <div className={styles.csrMeta}>{csr.organization || 'No Organization'}</div>
          </div>
          <Badge variant={getStatusVariant(csr.status)}>
            <Inline gap="xs" align="center">
              {getStatusIcon(csr.status)}
              <span>{csr.status}</span>
            </Inline>
          </Badge>
        </Inline>

        {/* Details */}
        <div className={styles.csrDetails}>
          <Grid cols={2} gap="xs">
            <div className={styles.csrDetailItem}>
              <span className={styles.csrDetailLabel}>Key Size:</span>
              <span>{csr.key_size} bits</span>
            </div>
            <div className={styles.csrDetailItem}>
              <span className={styles.csrDetailLabel}>Algorithm:</span>
              <span>{csr.algorithm}</span>
            </div>
            <div className={styles.csrDetailItem}>
              <span className={styles.csrDetailLabel}>Submitted:</span>
              <span>{csr.created_at}</span>
            </div>
            <div className={styles.csrDetailItem}>
              <span className={styles.csrDetailLabel}>By:</span>
              <span>{csr.submitted_by}</span>
            </div>
          </Grid>
        </div>

        {/* Actions */}
        <Inline gap="xs">
          <Button
            variant="secondary"
            size="sm"
            leftIcon={<Eye size={16} />}
            onClick={() => onView?.(csr)}
          >
            View
          </Button>
          {csr.status === 'pending' && (
            <Button
              variant="primary"
              size="sm"
              leftIcon={<Certificate size={16} />}
              onClick={() => onIssue?.(csr)}
            >
              Issue
            </Button>
          )}
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<Download size={16} />}
            onClick={() => {}}
          >
            Export
          </Button>
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<Trash size={16} />}
            onClick={() => onDelete?.(csr)}
          >
            Delete
          </Button>
        </Inline>
      </Stack>
    </Card>
  );
}

// CSR Details Modal
function CSRDetailsModal({ csr, isOpen, onClose, onIssue }) {
  if (!csr) return null;

  return (
    <Modal
      isOpen={isOpen}
      onClose={onClose}
      size="lg"
      title="CSR Details"
    >
      <Stack gap="lg">
        {/* Subject */}
        <div className={styles.modalSection}>
          <h3 className={styles.modalSectionTitle}>Subject</h3>
          <Grid cols={2} gap="md">
            <div className={styles.detailItem}>
              <div className={styles.detailLabel}>Common Name</div>
              <div className={styles.detailValue}>{csr.common_name}</div>
            </div>
            <div className={styles.detailItem}>
              <div className={styles.detailLabel}>Organization</div>
              <div className={styles.detailValue}>{csr.organization || 'N/A'}</div>
            </div>
            <div className={styles.detailItem}>
              <div className={styles.detailLabel}>Organizational Unit</div>
              <div className={styles.detailValue}>{csr.organizational_unit || 'N/A'}</div>
            </div>
            <div className={styles.detailItem}>
              <div className={styles.detailLabel}>Country</div>
              <div className={styles.detailValue}>{csr.country || 'N/A'}</div>
            </div>
          </Grid>
        </div>

        {/* Key Information */}
        <div className={styles.modalSection}>
          <h3 className={styles.modalSectionTitle}>Key Information</h3>
          <Grid cols={2} gap="md">
            <div className={styles.detailItem}>
              <div className={styles.detailLabel}>Algorithm</div>
              <div className={styles.detailValue}>{csr.algorithm}</div>
            </div>
            <div className={styles.detailItem}>
              <div className={styles.detailLabel}>Key Size</div>
              <div className={styles.detailValue}>{csr.key_size} bits</div>
            </div>
          </Grid>
        </div>

        {/* Subject Alternative Names */}
        {csr.san && csr.san.length > 0 && (
          <div className={styles.modalSection}>
            <h3 className={styles.modalSectionTitle}>Subject Alternative Names</h3>
            <Stack gap="xs">
              {csr.san.map((name, idx) => (
                <div key={idx} className={styles.sanItem}>
                  <GradientBadge variant="blue" size="sm">
                    {name}
                  </GradientBadge>
                </div>
              ))}
            </Stack>
          </div>
        )}

        {/* PEM Data */}
        <div className={styles.modalSection}>
          <h3 className={styles.modalSectionTitle}>PEM Data</h3>
          <div className={styles.pemData}>
            <pre>{csr.pem || 'No PEM data available'}</pre>
          </div>
        </div>

        <Inline gap="sm" justify="end">
          <Button variant="secondary" leftIcon={<Download size={18} />}>
            Download
          </Button>
          {csr.status === 'pending' && (
            <Button 
              variant="primary" 
              leftIcon={<Certificate size={18} />}
              onClick={() => onIssue?.(csr)}
            >
              Issue Certificate
            </Button>
          )}
        </Inline>
      </Stack>
    </Modal>
  );
}

export function CSRListV3() {
  const { data: csrs, isLoading } = useCSRs();

  const [selectedCSR, setSelectedCSR] = useState(null);
  const [detailsOpen, setDetailsOpen] = useState(false);

  const handleUpload = (files) => {
    console.log('Upload files:', files);
    // TODO: API call to parse and validate CSRs
  };

  const handleIssue = (csr) => {
    console.log('Issue certificate for CSR:', csr);
    // TODO: Navigate to certificate issuance page
  };

  const handleDelete = (csr) => {
    console.log('Delete CSR:', csr);
    // TODO: API call
  };

  const pendingCount = csrs?.filter(c => c.status === 'pending').length || 0;

  return (
    <div className={styles.container}>
      <Stack gap="xl">
        {/* Header */}
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>Certificate Signing Requests</h1>
            <p className={styles.subtitle}>
              {csrs?.length || 0} CSR{csrs?.length !== 1 ? 's' : ''} • {pendingCount} pending approval
            </p>
          </div>
        </div>

        {/* Upload Zone */}
        <GlassCard blur="md">
          <UploadZone onUpload={handleUpload} />
        </GlassCard>

        {/* Info Alert */}
        <Alert variant="info">
          <strong>How it works:</strong> Upload CSR files to validate and issue certificates. 
          Supported formats: PEM (.pem, .csr). Each CSR will be automatically parsed and validated.
        </Alert>

        {/* CSRs List */}
        {!csrs || csrs.length === 0 ? (
          <EmptyState
            icon={<FileText size={64} />}
            title="No CSRs"
            description="Upload CSR files to get started"
          />
        ) : (
          <Grid cols={2} gap="lg">
            {csrs.map((csr) => (
              <CSRCard
                key={csr.id}
                csr={csr}
                onView={(c) => { setSelectedCSR(c); setDetailsOpen(true); }}
                onIssue={handleIssue}
                onDelete={handleDelete}
              />
            ))}
          </Grid>
        )}
      </Stack>

      {/* Details Modal */}
      <CSRDetailsModal
        csr={selectedCSR}
        isOpen={detailsOpen}
        onClose={() => setDetailsOpen(false)}
        onIssue={handleIssue}
      />
    </div>
  );
}

export default CSRListV3;
