import { useState } from 'react';
import { classNames } from '../../utils/classNames';
import { Icon } from '../ui/Icon';
import { Badge } from '../ui/Badge';
import { getBadgeVariant } from '../../utils/getBadgeVariant';
import styles from './CAHierarchy.module.css';

/**
 * CANode Component
 * 
 * Single CA in the hierarchy tree
 * Features:
 * - Expand/collapse for children
 * - L-shaped connectors (left: 40px - exact prototype)
 * - CA card with badges
 * - Recursive rendering
 */
function CANode({ ca, level = 0, isLast = false, parentExpanded = true }) {
  const [expanded, setExpanded] = useState(true);
  const hasChildren = ca.children && ca.children.length > 0;

  return (
    <>
      <div className={styles.caRow} data-level={level}>
        {/* Connector lines */}
        {level > 0 && (
          <div className={styles.connector}>
            <div className={styles.connectorVertical} />
            <div className={styles.connectorHorizontal} />
            {!isLast && <div className={styles.connectorContinue} />}
          </div>
        )}

        {/* Expand button */}
        <div className={styles.caExpand}>
          {hasChildren && (
            <button
              onClick={() => setExpanded(!expanded)}
              className={styles.expandButton}
            >
              <Icon
                name={expanded ? 'caret-down' : 'caret-right'}
                size={16}
              />
            </button>
          )}
        </div>

        {/* CA Card */}
        <div className={styles.caCard}>
          <div className={styles.caIcon}>
            <Icon name="seal-check" size={20} gradient />
          </div>

          <div className={styles.caInfo}>
            <div className={styles.caName}>{ca.name}</div>
            <div className={styles.caDn}>{ca.dn}</div>
          </div>

          <div className={styles.caBadges}>
            <Badge variant={getBadgeVariant('ca-type', ca.type)}>
              {ca.type}
            </Badge>
            {ca.status && (
              <Badge variant={getBadgeVariant('ca-status', ca.status)}>
                {ca.status}
              </Badge>
            )}
          </div>
        </div>
      </div>

      {/* Recursive children */}
      {hasChildren && expanded && (
        <div className={styles.caChildren}>
          {ca.children.map((child, index) => (
            <CANode
              key={child.id}
              ca={child}
              level={level + 1}
              isLast={index === ca.children.length - 1}
              parentExpanded={expanded}
            />
          ))}
        </div>
      )}
    </>
  );
}

/**
 * CAHierarchy Component
 * 
 * Tree view of CAs with L-shaped connectors
 * 
 * Reference: prototype-cas.html
 * Connector calculation: left: 40px
 * - 20px expand button + 8px gap + 12px (half of 24px icon) = 40px
 */
export function CAHierarchy({ cas = [], className }) {
  if (cas.length === 0) {
    return (
      <div className={styles.emptyState}>
        <Icon name="tree-structure" size={48} color="tertiary" />
        <div className={styles.emptyText}>No certificate authorities found</div>
      </div>
    );
  }

  return (
    <div className={classNames(styles.hierarchy, className)}>
      {cas.map((ca, index) => (
        <CANode
          key={ca.id}
          ca={ca}
          level={0}
          isLast={index === cas.length - 1}
        />
      ))}
    </div>
  );
}

export default CAHierarchy;
