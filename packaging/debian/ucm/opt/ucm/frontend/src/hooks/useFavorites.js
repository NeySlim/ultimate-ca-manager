/**
 * useFavorites - Pin/favorite items for quick access
 * 
 * Stores favorites in localStorage by type.
 */
import { useState, useCallback, useEffect } from 'react'

const STORAGE_KEY = 'ucm-favorites'

/**
 * Get all favorites from localStorage
 */
function getStoredFavorites() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return stored ? JSON.parse(stored) : {}
  } catch {
    return {}
  }
}

/**
 * Save favorites to localStorage
 */
function saveFavorites(favorites) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(favorites))
  } catch {
    // Ignore storage errors
  }
}

/**
 * Hook to manage favorites for a specific type
 * @param {string} type - Type of items (e.g., 'certificates', 'cas', 'users')
 */
export function useFavorites(type) {
  const [favorites, setFavorites] = useState([])
  
  // Load initial state
  useEffect(() => {
    const allFavorites = getStoredFavorites()
    setFavorites(allFavorites[type] || [])
  }, [type])
  
  /**
   * Check if an item is favorited
   */
  const isFavorite = useCallback((id) => {
    return favorites.some(f => f.id === id)
  }, [favorites])
  
  /**
   * Toggle favorite status
   * @param {object} item - Item to toggle { id, name, subtitle? }
   */
  const toggleFavorite = useCallback((item) => {
    if (!item?.id) return
    
    const allFavorites = getStoredFavorites()
    const typeFavorites = allFavorites[type] || []
    
    const exists = typeFavorites.some(f => f.id === item.id)
    
    let updated
    if (exists) {
      // Remove from favorites
      updated = typeFavorites.filter(f => f.id !== item.id)
    } else {
      // Add to favorites
      const newFavorite = {
        id: item.id,
        name: item.name || item.common_name || item.cn || item.username || `Item ${item.id}`,
        subtitle: item.subtitle || item.email || item.issuer || '',
        type,
        addedAt: Date.now()
      }
      updated = [newFavorite, ...typeFavorites]
    }
    
    allFavorites[type] = updated
    saveFavorites(allFavorites)
    setFavorites(updated)
    
    return !exists // Returns new favorite status
  }, [type, favorites])
  
  /**
   * Remove from favorites
   */
  const removeFavorite = useCallback((id) => {
    const allFavorites = getStoredFavorites()
    const typeFavorites = allFavorites[type] || []
    const updated = typeFavorites.filter(f => f.id !== id)
    allFavorites[type] = updated
    saveFavorites(allFavorites)
    setFavorites(updated)
  }, [type])
  
  return {
    favorites,
    isFavorite,
    toggleFavorite,
    removeFavorite
  }
}

/**
 * Hook to get all favorites across all types
 */
export function useAllFavorites() {
  const [allFavorites, setAllFavorites] = useState([])
  
  const refreshFavorites = useCallback(() => {
    const favorites = getStoredFavorites()
    
    // Flatten all types into a single array
    const all = Object.entries(favorites).flatMap(([type, items]) => 
      items.map(item => ({ ...item, type }))
    )
    
    // Sort by addedAt (most recent first)
    all.sort((a, b) => (b.addedAt || 0) - (a.addedAt || 0))
    
    setAllFavorites(all)
  }, [])
  
  useEffect(() => {
    refreshFavorites()
  }, [refreshFavorites])
  
  return { allFavorites, refreshFavorites }
}
