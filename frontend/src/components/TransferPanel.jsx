/**
 * TransferPanel - Generic dual-list basket/transfer component
 * 
 * Two columns: Available items (left) → Selected basket (right)
 * Supports drag & drop, click transfer, bulk operations, search
 * 
 * Based on MemberTransferModal pattern but generic for any data type.
 */
import { useState, useMemo, useCallback, useRef } from 'react'
import { useTranslation } from 'react-i18next'
import {
  MagnifyingGlass, Plus, Minus, CaretRight, CaretLeft,
  CaretDoubleRight, CaretDoubleLeft, ShoppingCart, Package
} from '@phosphor-icons/react'
import { Button } from './Button'
import { cn } from '../lib/utils'

function TransferItem({ item, renderItem, onAction, actionIcon: ActionIcon, actionVariant, draggable, from, onDragStart }) {
  return (
    <div
      draggable={draggable}
      onDragStart={draggable ? (e) => onDragStart(e, item, from) : undefined}
      className={cn(
        "flex items-center gap-2 px-2.5 py-2 rounded-lg transition-all group",
        "hover:bg-bg-tertiary border border-transparent",
        draggable && "cursor-grab active:cursor-grabbing"
      )}
    >
      {/* Item content via render function */}
      <div className="flex-1 min-w-0">
        {renderItem(item)}
      </div>

      {/* Action button */}
      <button
        onClick={(e) => { e.stopPropagation(); onAction(item.id) }}
        className={cn(
          "p-1.5 rounded-lg transition-all opacity-0 group-hover:opacity-100",
          actionVariant === 'add' && "text-accent-success hover:bg-accent-success-op10",
          actionVariant === 'remove' && "text-accent-danger hover:bg-accent-danger-op10"
        )}
      >
        <ActionIcon size={16} weight="bold" />
      </button>
    </div>
  )
}

export function TransferPanel({
  items = [],
  selectedIds = new Set(),
  onSelectionChange,
  renderItem,
  searchKeys = ['name'],
  leftTitle,
  rightTitle,
  leftIcon: LeftIcon = Package,
  rightIcon: RightIcon = ShoppingCart,
  emptyLeftMessage,
  emptyRightMessage,
  bulkActions,
  className,
}) {
  const { t } = useTranslation()
  const [searchLeft, setSearchLeft] = useState('')
  const [searchRight, setSearchRight] = useState('')
  const draggedRef = useRef(null)
  const [dragOver, setDragOver] = useState(null)

  const leftLabel = leftTitle || t('operations.available', 'Available')
  const rightLabel = rightTitle || t('operations.basket', 'Basket')
  const emptyLeft = emptyLeftMessage || t('operations.allSelected', 'All items in basket')
  const emptyRight = emptyRightMessage || t('operations.dragHere', 'Drag items here or click + to add')

  // Filter items
  const filterBySearch = useCallback((list, search) => {
    if (!search) return list
    const s = search.toLowerCase()
    return list.filter(item =>
      searchKeys.some(key => {
        const val = item[key]
        return val && String(val).toLowerCase().includes(s)
      })
    )
  }, [searchKeys])

  const availableItems = useMemo(() =>
    filterBySearch(items.filter(i => !selectedIds.has(i.id)), searchLeft),
    [items, selectedIds, searchLeft, filterBySearch]
  )

  const basketItems = useMemo(() =>
    filterBySearch(items.filter(i => selectedIds.has(i.id)), searchRight),
    [items, selectedIds, searchRight, filterBySearch]
  )

  const totalBasket = useMemo(() =>
    items.filter(i => selectedIds.has(i.id)).length,
    [items, selectedIds]
  )

  // Transfer actions
  const addItem = useCallback((id) => {
    const next = new Set(selectedIds)
    next.add(id)
    onSelectionChange(next)
  }, [selectedIds, onSelectionChange])

  const removeItem = useCallback((id) => {
    const next = new Set(selectedIds)
    next.delete(id)
    onSelectionChange(next)
  }, [selectedIds, onSelectionChange])

  const addAll = useCallback(() => {
    const next = new Set(selectedIds)
    availableItems.forEach(i => next.add(i.id))
    onSelectionChange(next)
  }, [selectedIds, availableItems, onSelectionChange])

  const removeAll = useCallback(() => {
    const basketIds = new Set(basketItems.map(i => i.id))
    const next = new Set([...selectedIds].filter(id => !basketIds.has(id)))
    onSelectionChange(next)
  }, [selectedIds, basketItems, onSelectionChange])

  // Drag handlers
  const handleDragStart = (e, item, from) => {
    draggedRef.current = { item, from }
    e.dataTransfer.effectAllowed = 'move'
    e.dataTransfer.setData('text/plain', item.id.toString())
  }

  const handleDragOver = (e, target) => {
    e.preventDefault()
    e.dataTransfer.dropEffect = 'move'
    setDragOver(target)
  }

  const handleDragLeave = () => setDragOver(null)

  const handleDrop = (e, target) => {
    e.preventDefault()
    setDragOver(null)
    if (!draggedRef.current) return
    const { item, from } = draggedRef.current
    if (from === 'available' && target === 'basket') addItem(item.id)
    else if (from === 'basket' && target === 'available') removeItem(item.id)
    draggedRef.current = null
  }

  const SearchInput = ({ value, onChange, placeholder }) => (
    <div className="relative">
      <MagnifyingGlass size={14} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-text-tertiary" />
      <input
        type="text"
        placeholder={placeholder || t('common.search') + '...'}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full pl-8 pr-3 py-1.5 text-xs bg-bg-tertiary border border-border rounded-md text-text-primary placeholder:text-text-tertiary focus:outline-none focus:ring-1 focus:ring-accent-primary"
      />
    </div>
  )

  return (
    <div className={cn("flex flex-col h-full min-h-0", className)}>
      {/* Two-column transfer area */}
      <div className="flex-1 flex gap-2 min-h-0">
        {/* Left: Available items */}
        <div
          className={cn(
            "flex-1 flex flex-col border rounded-xl overflow-hidden transition-colors min-w-0",
            dragOver === 'available' ? "border-accent-primary bg-accent-primary-op5" : "border-border"
          )}
          onDragOver={(e) => handleDragOver(e, 'available')}
          onDragLeave={handleDragLeave}
          onDrop={(e) => handleDrop(e, 'available')}
        >
          <div className="px-3 py-2.5 bg-secondary-op50 border-b border-border space-y-2 shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <LeftIcon size={16} className="text-text-tertiary" />
                <span className="text-sm font-medium text-text-primary">{leftLabel}</span>
              </div>
              <span className="text-xs font-medium px-2 py-0.5 rounded-full bg-bg-tertiary text-text-secondary">
                {availableItems.length}
              </span>
            </div>
            <SearchInput value={searchLeft} onChange={setSearchLeft} />
          </div>
          <div className="flex-1 overflow-auto p-1.5 space-y-0.5">
            {availableItems.length === 0 ? (
              <p className="text-xs text-text-tertiary text-center py-8">{emptyLeft}</p>
            ) : (
              availableItems.map(item => (
                <TransferItem
                  key={item.id}
                  item={item}
                  renderItem={renderItem}
                  onAction={addItem}
                  actionIcon={Plus}
                  actionVariant="add"
                  draggable
                  from="available"
                  onDragStart={handleDragStart}
                />
              ))
            )}
          </div>
        </div>

        {/* Center: Transfer buttons */}
        <div className="flex flex-col items-center justify-center gap-1.5 px-1 shrink-0">
          <Button type="button" size="sm" variant="secondary" onClick={addAll} disabled={availableItems.length === 0}
            title={t('operations.addAll', 'Add all')} className="w-8 h-8 p-0">
            <CaretDoubleRight size={14} />
          </Button>
          <Button type="button" size="sm" variant="secondary" onClick={() => {}}
            disabled title="" className="w-8 h-8 p-0 invisible">
            <CaretRight size={14} />
          </Button>
          <Button type="button" size="sm" variant="secondary" onClick={() => {}}
            disabled title="" className="w-8 h-8 p-0 invisible">
            <CaretLeft size={14} />
          </Button>
          <Button type="button" size="sm" variant="secondary" onClick={removeAll} disabled={totalBasket === 0}
            title={t('operations.removeAll', 'Remove all')} className="w-8 h-8 p-0">
            <CaretDoubleLeft size={14} />
          </Button>
        </div>

        {/* Right: Basket (selected items) */}
        <div
          className={cn(
            "flex-1 flex flex-col border rounded-xl overflow-hidden transition-colors min-w-0",
            dragOver === 'basket' ? "border-accent-primary bg-accent-primary-op5" : "border-border",
            totalBasket > 0 && "border-accent-primary-op30"
          )}
          onDragOver={(e) => handleDragOver(e, 'basket')}
          onDragLeave={handleDragLeave}
          onDrop={(e) => handleDrop(e, 'basket')}
        >
          <div className="px-3 py-2.5 bg-secondary-op50 border-b border-border space-y-2 shrink-0">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <RightIcon size={16} className={totalBasket > 0 ? "text-accent-primary" : "text-text-tertiary"} />
                <span className="text-sm font-medium text-text-primary">{rightLabel}</span>
              </div>
              <span className={cn(
                "text-xs font-medium px-2 py-0.5 rounded-full",
                totalBasket > 0 ? "bg-accent-primary-op20 text-accent-primary" : "bg-bg-tertiary text-text-secondary"
              )}>
                {totalBasket}
              </span>
            </div>
            <SearchInput value={searchRight} onChange={setSearchRight} />
          </div>
          <div className="flex-1 overflow-auto p-1.5 space-y-0.5">
            {basketItems.length === 0 ? (
              <div className="flex flex-col items-center justify-center py-8 gap-2">
                <ShoppingCart size={32} className="text-tertiary-op50" />
                <p className="text-xs text-text-tertiary text-center">{emptyRight}</p>
              </div>
            ) : (
              basketItems.map(item => (
                <TransferItem
                  key={item.id}
                  item={item}
                  renderItem={renderItem}
                  onAction={removeItem}
                  actionIcon={Minus}
                  actionVariant="remove"
                  draggable
                  from="basket"
                  onDragStart={handleDragStart}
                />
              ))
            )}
          </div>
        </div>
      </div>

      {/* Bottom: Bulk action buttons */}
      {totalBasket > 0 && bulkActions && (
        <div className="shrink-0 flex items-center justify-between px-3 py-2.5 mt-2 rounded-xl border border-border bg-secondary-op50">
          <span className="text-sm text-text-secondary">
            {totalBasket} {t('operations.itemsSelected', 'item(s) selected')}
          </span>
          <div className="flex items-center gap-2">
            {bulkActions}
          </div>
        </div>
      )}
    </div>
  )
}

export default TransferPanel
