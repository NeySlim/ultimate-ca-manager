import { classNames } from '../../utils/classNames';
import { Input } from '../ui/Input';
import { Button } from '../ui/Button';
import { Icon } from '../ui/Icon';
import styles from './SearchToolbar.module.css';

/**
 * SearchToolbar Component
 * 
 * Toolbar with:
 * - Search input with icon
 * - Filter dropdowns (optional)
 * - Action buttons (create, export, refresh, etc.)
 * 
 * Layout: flex justify-between
 * Left: Search + filters
 * Right: Actions
 */
export function SearchToolbar({
  searchValue,
  onSearchChange,
  searchPlaceholder = 'Search...',
  filters = [],
  actions = [],
  className,
}) {
  return (
    <div className={classNames(styles.toolbar, className)}>
      <div className={styles.toolbarLeft}>
        <Input
          type="search"
          value={searchValue}
          onChange={onSearchChange}
          placeholder={searchPlaceholder}
          icon="ph ph-magnifying-glass"
          className={styles.searchInput}
        />

        {filters.length > 0 && (
          <div className={styles.filters}>
            {filters.map((filter, index) => (
              <select
                key={index}
                value={filter.value}
                onChange={(e) => filter.onChange(e.target.value)}
                className={styles.filterSelect}
              >
                <option value="">{filter.placeholder || 'All'}</option>
                {filter.options.map((option) => (
                  <option key={option.value} value={option.value}>
                    {option.label}
                  </option>
                ))}
              </select>
            ))}
          </div>
        )}
      </div>

      {actions.length > 0 && (
        <div className={styles.toolbarRight}>
          {actions.map((action, index) => (
            <Button
              key={index}
              variant={action.variant || 'default'}
              icon={action.icon}
              onClick={action.onClick}
            >
              {action.label}
            </Button>
          ))}
        </div>
      )}
    </div>
  );
}

export default SearchToolbar;
