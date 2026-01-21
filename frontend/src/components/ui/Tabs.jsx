import { Tab as HeadlessTab } from '@headlessui/react';
import { classNames } from '../../utils/classNames';
import styles from './Tabs.module.css';

/**
 * Tabs Component
 * Wrapper around Headless UI Tabs with UCM styling
 */
export function Tabs({ children, className, ...props }) {
  return (
    <HeadlessTab.Group as="div" className={classNames(styles.tabs, className)} {...props}>
      {children}
    </HeadlessTab.Group>
  );
}

Tabs.List = function TabList({ children, className, ...props }) {
  return (
    <HeadlessTab.List className={classNames(styles.tabList, className)} {...props}>
      {children}
    </HeadlessTab.List>
  );
};

Tabs.Tab = function Tab({ children, className, ...props }) {
  return (
    <HeadlessTab
      className={({ selected }) =>
        classNames(
          styles.tab,
          selected && styles.selected,
          className
        )
      }
      {...props}
    >
      {children}
    </HeadlessTab>
  );
};

Tabs.Panels = function TabPanels({ children, className, ...props }) {
  return (
    <HeadlessTab.Panels className={classNames(styles.tabPanels, className)} {...props}>
      {children}
    </HeadlessTab.Panels>
  );
};

Tabs.Panel = function TabPanel({ children, className, ...props }) {
  return (
    <HeadlessTab.Panel className={classNames(styles.tabPanel, className)} {...props}>
      {children}
    </HeadlessTab.Panel>
  );
};

export default Tabs;
