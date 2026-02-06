/**
 * Shared Hooks for Common Patterns
 * Reduces code duplication across pages
 */
import { useState, useCallback } from 'react'
import { useNotification } from '../contexts/NotificationContext'

/**
 * Hook for handling delete operations with confirmation
 */
export function useDeleteHandler(entityName, deleteService, onSuccess) {
  const { showConfirm, showSuccess, showError } = useNotification()
  const [deleting, setDeleting] = useState(false)

  const handleDelete = useCallback(async (id, customMessage) => {
    const confirmed = await showConfirm(
      customMessage || `Are you sure you want to delete this ${entityName.toLowerCase()}?`,
      {
        title: `Delete ${entityName}`,
        confirmText: 'Delete',
        variant: 'danger'
      }
    )
    if (!confirmed) return false

    setDeleting(true)
    try {
      await deleteService(id)
      showSuccess(`${entityName} deleted successfully`)
      onSuccess?.()
      return true
    } catch (error) {
      showError(error.message || `Failed to delete ${entityName.toLowerCase()}`)
      return false
    } finally {
      setDeleting(false)
    }
  }, [entityName, deleteService, onSuccess, showConfirm, showSuccess, showError])

  return { handleDelete, deleting }
}

/**
 * Hook for form state management with nested updates
 */
export function useFormData(initialData) {
  const [formData, setFormData] = useState(initialData)

  const updateField = useCallback((field, value) => {
    setFormData(prev => ({ ...prev, [field]: value }))
  }, [])

  const updateNested = useCallback((parent, field, value) => {
    setFormData(prev => ({
      ...prev,
      [parent]: { ...prev[parent], [field]: value }
    }))
  }, [])

  const resetForm = useCallback(() => {
    setFormData(initialData)
  }, [initialData])

  return { formData, setFormData, updateField, updateNested, resetForm }
}

/**
 * Hook for managing multiple modals
 */
export function useModals(modalNames = []) {
  const initialState = modalNames.reduce((acc, name) => ({ ...acc, [name]: false }), {})
  const [modals, setModals] = useState(initialState)

  const open = useCallback((name) => {
    setModals(prev => ({ ...prev, [name]: true }))
  }, [])

  const close = useCallback((name) => {
    setModals(prev => ({ ...prev, [name]: false }))
  }, [])

  const toggle = useCallback((name) => {
    setModals(prev => ({ ...prev, [name]: !prev[name] }))
  }, [])

  const closeAll = useCallback(() => {
    setModals(initialState)
  }, [initialState])

  return { modals, open, close, toggle, closeAll }
}

/**
 * Hook for pagination state
 */
export function usePagination(defaultPerPage = 20) {
  const [page, setPage] = useState(1)
  const [perPage, setPerPage] = useState(defaultPerPage)
  const [total, setTotal] = useState(0)

  const totalPages = Math.ceil(total / perPage)
  
  const goToPage = useCallback((newPage) => {
    setPage(Math.max(1, Math.min(newPage, totalPages || 1)))
  }, [totalPages])

  const nextPage = useCallback(() => {
    if (page < totalPages) setPage(p => p + 1)
  }, [page, totalPages])

  const prevPage = useCallback(() => {
    if (page > 1) setPage(p => p - 1)
  }, [page])

  const reset = useCallback(() => {
    setPage(1)
  }, [])

  return {
    page,
    perPage,
    total,
    totalPages,
    setPage: goToPage,
    setPerPage,
    setTotal,
    nextPage,
    prevPage,
    reset,
  }
}

/**
 * Hook for async data loading with error handling
 */
export function useAsyncData(loadFn, dependencies = []) {
  const [data, setData] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const { showError } = useNotification()

  const load = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const result = await loadFn()
      setData(result)
    } catch (err) {
      setError(err)
      showError(err.message || 'Failed to load data')
    } finally {
      setLoading(false)
    }
  }, [loadFn, showError])

  return { data, loading, error, load, setData }
}
