/**
 * useRecentHistory - Track recently viewed items
 * 
 * Stores recent items in localStorage with automatic cleanup.
 * Items are stored per type (certificates, cas, users, etc.)
 */
import { useState, useCallback, useEffect } from 'react'

const MAX_RECENT_ITEMS = 10
const STORAGE_KEY = 'ucm-recent-history'

/**
 * Get all recent history from localStorage
 */
function getStoredHistory() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored ? JSON.parse(stored) : {}
  } catch {
    return {}
  }
}

/**
 * Save history to localStorage
 */
function saveHistory(history) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(history))
  } catch {
    // Ignore storage errors
  }
}

/**
 * Hook to manage recent history for a specific type
 * @param {string} type - Type of items (e.g., 'certificates', 'cas', 'users')
 */
export function useRecentHistory(type) {
  const [recentItems, setRecentItems] = useState([])
  
  // Load initial state
  useEffect(() => {
    const history = getStoredHistory()
    setRecentItems(history[type] || [])
  }, [type])
  
  /**
   * Add an item to recent history
   * @param {object} item - Item to add { id, name, subtitle?, icon? }
   */
  const addToHistory = useCallback((item) => {
    if (!item?.id) return
    
    const history = getStoredHistory()
    const typeHistory = history[type] || []
    
    // Create new item with timestamp
    const newItem = {
      id: item.id,
      name: item.name || item.common_name || item.cn || item.username || `Item ${item.id}`,
      subtitle: item.subtitle || item.email || item.issuer || '',
      type,
      timestamp: Date.now()
    }
    
    // Remove existing entry for this item
    const filtered = typeHistory.filter(i => i.id !== item.id)
    
    // Add new item at the beginning
    const updated = [newItem, ...filtered].slice(0, MAX_RECENT_ITEMS)
    
    // Save
    history[type] = updated
    saveHistory(history)
    setRecentItems(updated)
  }, [type])
  
  /**
   * Clear history for this type
   */
  const clearHistory = useCallback(() => {
    const history = getStoredHistory()
    delete history[type]
    saveHistory(history)
    setRecentItems([])
  }, [type])
  
  /**
   * Remove a single item from history
   */
  const removeFromHistory = useCallback((id) => {
    const history = getStoredHistory()
    const typeHistory = history[type] || []
    const updated = typeHistory.filter(i => i.id !== id)
    history[type] = updated
    saveHistory(history)
    setRecentItems(updated)
  }, [type])
  
  return {
    recentItems,
    addToHistory,
    clearHistory,
    removeFromHistory
  }
}

/**
 * Hook to get all recent history across all types
 */
export function useAllRecentHistory() {
  const [allRecent, setAllRecent] = useState([])
  
  useEffect(() => {
    const history = getStoredHistory()
    
    // Flatten all types into a single array
    const all = Object.entries(history).flatMap(([type, items]) => 
      items.map(item => ({ ...item, type }))
    )
    
    // Sort by timestamp (most recent first)
    all.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
    
    setAllRecent(all.slice(0, MAX_RECENT_ITEMS * 2)) // Allow more for global view
  }, [])
  
  const refreshHistory = useCallback(() => {
    const history = getStoredHistory()
    const all = Object.entries(history).flatMap(([type, items]) => 
      items.map(item => ({ ...item, type }))
    )
    all.sort((a, b) => (b.timestamp || 0) - (a.timestamp || 0))
    setAllRecent(all.slice(0, MAX_RECENT_ITEMS * 2))
  }, [])
  
  return { allRecent, refreshHistory }
}
