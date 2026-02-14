/**
 * File Upload Component
 */
import { useState, useId } from 'react'
import { useTranslation } from 'react-i18next'
import { UploadSimple, FileText, X } from '@phosphor-icons/react'
import { cn } from '../lib/utils'
import { Button } from './Button'

export function FileUpload({ 
  accept, 
  multiple = false, 
  onUpload,
  onFileSelect, // Called immediately when file is selected (no upload button)
  helperText,
  label,
  compact = false, // Compact mode: smaller drop zone
  maxSize = 10 * 1024 * 1024, // 10MB default
  className 
}) {
  const { t } = useTranslation()
  const inputId = useId()
  const [isDragging, setIsDragging] = useState(false)
  const [files, setFiles] = useState([])
  const [error, setError] = useState(null)

  const handleDragOver = (e) => {
    e.preventDefault()
    setIsDragging(true)
  }

  const handleDragLeave = () => {
    setIsDragging(false)
  }

  const validateFile = (file) => {
    if (maxSize && file.size > maxSize) {
      return `File size exceeds ${(maxSize / 1024 / 1024).toFixed(0)}MB`
    }
    return null
  }

  const handleFiles = (fileList) => {
    setError(null)
    const newFiles = Array.from(fileList)
    
    for (const file of newFiles) {
      const error = validateFile(file)
      if (error) {
        setError(error)
        return
      }
    }

    if (multiple) {
      setFiles(prev => [...prev, ...newFiles])
    } else {
      setFiles(newFiles)
    }
    
    // If onFileSelect is provided, call it immediately (for modals, etc.)
    if (onFileSelect) {
      onFileSelect(multiple ? newFiles : newFiles[0])
    }
  }

  const handleDrop = (e) => {
    e.preventDefault()
    setIsDragging(false)
    handleFiles(e.dataTransfer.files)
  }

  const handleInputChange = (e) => {
    if (e.target.files) {
      handleFiles(e.target.files)
    }
  }

  const removeFile = (index) => {
    setFiles(prev => prev.filter((_, i) => i !== index))
  }

  const handleUpload = async () => {
    if (files.length === 0) return
    if (!onUpload) return // No upload handler, just use onFileSelect
    
    try {
      await onUpload(files)
      setFiles([])
    } catch (err) {
      setError(err.message)
    }
  }

  return (
    <div className={cn("space-y-4", className)}>
      {label && (
        <label className="block text-sm font-medium text-text-primary">{label}</label>
      )}
      <div
        onDragOver={handleDragOver}
        onDragLeave={handleDragLeave}
        onDrop={handleDrop}
        className={cn(
          "border-2 border-dashed rounded-xl text-center transition-all cursor-pointer",
          compact ? "p-4" : "p-8",
          isDragging 
            ? "border-accent-primary bg-accent-primary/10" 
            : "border-border hover:border-accent-primary/50"
        )}
      >
        <input
          type="file"
          accept={accept}
          multiple={multiple}
          onChange={handleInputChange}
          className="hidden"
          id={inputId}
        />
        
        <label htmlFor={inputId} className="cursor-pointer">
          <UploadSimple size={compact ? 28 : 48} className="mx-auto mb-2 text-text-secondary" weight="duotone" />
          <p className={cn("font-medium text-text-primary mb-1", compact ? "text-xs" : "text-sm")}>
            {t('common.dropFilesOrBrowse')}
          </p>
          <p className="text-xs text-text-secondary">
            {helperText || `${accept || t('common.anyFile')} • Max ${(maxSize / 1024 / 1024).toFixed(0)}MB`}
          </p>
        </label>
      </div>

      {error && (
        <div className="p-3 status-danger-bg status-danger-border border rounded-lg text-sm status-danger-text">
          {error}
        </div>
      )}

      {files.length > 0 && !onFileSelect && (
        <div className="space-y-2">
          {files.map((file, index) => (
            <div
              key={file.name}
              className="flex items-center gap-3 p-3 bg-bg-tertiary border border-border rounded-lg"
            >
              <FileText size={20} className="text-text-secondary flex-shrink-0" />
              <div className="flex-1 min-w-0">
                <p className="text-sm font-medium text-text-primary truncate">{file.name}</p>
                <p className="text-xs text-text-secondary">
                  {(file.size / 1024).toFixed(1)} KB
                </p>
              </div>
              <button
                onClick={() => removeFile(index)}
                className="text-text-secondary hover:status-danger-text transition-colors flex-shrink-0"
              >
                <X size={16} />
              </button>
            </div>
          ))}

          {onUpload && (
            <Button onClick={handleUpload} className="w-full">
              Upload {files.length} file{files.length > 1 ? 's' : ''}
            </Button>
          )}
        </div>
      )}
    </div>
  )
}
