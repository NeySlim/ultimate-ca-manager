/**
 * TreeView Component - Hierarchical tree for CAs
 */
import { useState } from 'react'
import { CaretRight, CaretDown } from '@phosphor-icons/react'
import { cn } from '../lib/utils'

export function TreeView({ nodes, onSelect, selectedId }) {
  return (
    <div className="space-y-0.5">
      {nodes.map(node => (
        <TreeNode
          key={node.id}
          node={node}
          level={0}
          onSelect={onSelect}
          selectedId={selectedId}
        />
      ))}
    </div>
  )
}

function TreeNode({ node, level, onSelect, selectedId }) {
  const [isExpanded, setIsExpanded] = useState(true)
  const hasChildren = node.children && node.children.length > 0
  const isSelected = node.id === selectedId

  return (
    <div>
      <div
        className={cn(
          "flex items-center gap-1.5 px-2 py-1 rounded-sm cursor-pointer transition-colors group",
          isSelected 
            ? "bg-accent-primary/20 text-accent-primary" 
            : "hover:bg-bg-tertiary text-text-primary"
        )}
        style={{ paddingLeft: `${level * 16 + 8}px` }}
        onClick={() => onSelect?.(node)}
      >
        {hasChildren && (
          <button
            onClick={(e) => {
              e.stopPropagation()
              setIsExpanded(!isExpanded)
            }}
            className="flex-shrink-0 text-text-secondary hover:text-text-primary"
          >
            {isExpanded ? (
              <CaretDown size={14} weight="bold" />
            ) : (
              <CaretRight size={14} weight="bold" />
            )}
          </button>
        )}
        
        {!hasChildren && <div className="w-3.5" />}
        
        {node.icon && (
          <span className="flex-shrink-0">
            {node.icon}
          </span>
        )}
        
        <span className="flex-1 text-sm font-medium truncate">
          {node.name}
        </span>
        
        {node.badge && (
          <span className="flex-shrink-0 px-1 py-0.5 text-xs bg-bg-tertiary rounded-sm">
            {node.badge}
          </span>
        )}
      </div>

      {hasChildren && isExpanded && (
        <div className="space-y-0.5">
          {node.children.map(child => (
            <TreeNode
              key={child.id}
              node={child}
              level={level + 1}
              onSelect={onSelect}
              selectedId={selectedId}
            />
          ))}
        </div>
      )}
    </div>
  )
}
