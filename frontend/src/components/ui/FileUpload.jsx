import { useState, useRef } from 'react';
import { UploadSimple, File, X } from '@phosphor-icons/react';
import styles from './FileUpload.module.css';

export function FileUpload({ 
  value,
  onChange,
  accept = '*',
  maxSize = 10 * 1024 * 1024, // 10MB default
  disabled = false,
  error = null
}) {
  const [isDragging, setIsDragging] = useState(false);
  const fileInputRef = useRef(null);

  const handleDragEnter = (e) => {
    e.preventDefault();
    e.stopPropagation();
    if (!disabled) setIsDragging(true);
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

    if (disabled) return;

    const files = e.dataTransfer.files;
    if (files && files.length > 0) {
      handleFile(files[0]);
    }
  };

  const handleFileSelect = (e) => {
    const files = e.target.files;
    if (files && files.length > 0) {
      handleFile(files[0]);
    }
  };

  const handleFile = (file) => {
    if (file.size > maxSize) {
      onChange(null, `File too large. Max size: ${Math.round(maxSize / 1024 / 1024)}MB`);
      return;
    }

    onChange(file, null);
  };

  const handleRemove = () => {
    onChange(null, null);
    if (fileInputRef.current) {
      fileInputRef.current.value = '';
    }
  };

  const handleClick = () => {
    if (!disabled && fileInputRef.current) {
      fileInputRef.current.click();
    }
  };

  const formatFileSize = (bytes) => {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
  };

  return (
    <div className={styles.container}>
      <input
        ref={fileInputRef}
        type="file"
        accept={accept}
        onChange={handleFileSelect}
        disabled={disabled}
        className={styles.hiddenInput}
      />

      {!value ? (
        <div
          className={`${styles.dropzone} ${isDragging ? styles.dragging : ''} ${disabled ? styles.disabled : ''} ${error ? styles.error : ''}`}
          onDragEnter={handleDragEnter}
          onDragLeave={handleDragLeave}
          onDragOver={handleDragOver}
          onDrop={handleDrop}
          onClick={handleClick}
        >
          <UploadSimple size={32} className={styles.icon} />
          <div className={styles.text}>
            <p className={styles.primary}>
              {isDragging ? 'Drop file here' : 'Click to browse or drag and drop'}
            </p>
            <p className={styles.secondary}>
              Max file size: {Math.round(maxSize / 1024 / 1024)}MB
            </p>
          </div>
        </div>
      ) : (
        <div className={styles.preview}>
          <File size={24} className={styles.fileIcon} />
          <div className={styles.fileInfo}>
            <p className={styles.fileName}>{value.name}</p>
            <p className={styles.fileSize}>{formatFileSize(value.size)}</p>
          </div>
          {!disabled && (
            <button
              type="button"
              onClick={handleRemove}
              className={styles.removeBtn}
              title="Remove file"
            >
              <X size={16} />
            </button>
          )}
        </div>
      )}

      {error && (
        <p className={styles.errorText}>{error}</p>
      )}
    </div>
  );
}
