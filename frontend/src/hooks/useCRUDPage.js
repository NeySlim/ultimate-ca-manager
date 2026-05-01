import { useState, useEffect, useCallback } from 'react'
import { useNotification } from '../contexts'

/**
 * useCRUDPage - shared state and handlers for CRUD management pages.
 *
 * @param {Object} options
 * @param {Function} options.loadFn       - async fn that returns the items array (already unwrapped: res.data)
 * @param {string}   [options.loadErrorMsg] - fallback i18n message key or string shown on load failure
 * @returns {Object} CRUD state + handlers
 */
export function useCRUDPage({ loadFn, loadErrorMsg = 'Failed to load data' }) {
  const { showError } = useNotification()

  const [items, setItems] = useState([])
  const [loading, setLoading] = useState(true)
  const [selectedItem, setSelectedItem] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [editing, setEditing] = useState(null)
  const [saving, setSaving] = useState(false)
  const [deleteTarget, setDeleteTarget] = useState(null)

  const loadData = useCallback(async () => {
    try {
      setLoading(true)
      const result = await loadFn()
      setItems(Array.isArray(result) ? result : [])
    } catch (err) {
      showError(err.message || loadErrorMsg)
    } finally {
      setLoading(false)
    }
  }, []) // intentionally empty deps — loadFn is stable (wrapped in useCallback in caller)

  useEffect(() => { loadData() }, [loadData])

  const openCreateModal = useCallback(() => { setEditing(null); setShowModal(true) }, [])
  const openEditModal = useCallback((item) => { setEditing(item); setShowModal(true) }, [])
  const closeModal = useCallback(() => { setShowModal(false); setEditing(null) }, [])

  return {
    items, setItems,
    loading,
    selectedItem, setSelectedItem,
    showModal, setShowModal,
    editing, setEditing,
    saving, setSaving,
    deleteTarget, setDeleteTarget,
    loadData,
    openCreateModal,
    openEditModal,
    closeModal,
  }
}
