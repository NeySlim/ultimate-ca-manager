import React, { Fragment } from 'react';
import { Menu as HeadlessMenu, Transition } from '@headlessui/react';
import './Menu.css';

/**
 * Menu component - Headless UI Menu
 * Replaces Mantine Menu with dropdown functionality
 */
export const Menu = ({ children, trigger }) => {
  return (
    <HeadlessMenu as="div" className="menu-container">
      <HeadlessMenu.Button as={Fragment}>
        {trigger}
      </HeadlessMenu.Button>

      <Transition
        as={Fragment}
        enter="menu-transition-enter"
        enterFrom="menu-transition-enter-from"
        enterTo="menu-transition-enter-to"
        leave="menu-transition-leave"
        leaveFrom="menu-transition-leave-from"
        leaveTo="menu-transition-leave-to"
      >
        <HeadlessMenu.Items className="menu-dropdown">
          {children}
        </HeadlessMenu.Items>
      </Transition>
    </HeadlessMenu>
  );
};

export const MenuItem = ({ children, onClick, icon }) => {
  return (
    <HeadlessMenu.Item>
      {({ active }) => (
        <button
          className={`menu-item ${active ? 'menu-item-active' : ''}`}
          onClick={onClick}
        >
          {icon && <span className="menu-item-icon">{icon}</span>}
          <span className="menu-item-label">{children}</span>
        </button>
      )}
    </HeadlessMenu.Item>
  );
};

export const MenuDivider = () => <div className="menu-divider" />;
