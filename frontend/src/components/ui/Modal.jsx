import React, { Fragment } from 'react';
import { Dialog, Transition } from '@headlessui/react';
import { X } from '@phosphor-icons/react';
import { Button } from './Button';
import './Modal.css';

/**
 * Modal component - Headless UI Dialog
 * Replaces Mantine Modal
 */
export const Modal = ({ 
  open, 
  onClose, 
  title, 
  children,
  size = 'md',
  footer
}) => {
  const sizeMap = {
    xs: 'modal-xs',
    sm: 'modal-sm',
    md: 'modal-md',
    lg: 'modal-lg',
    xl: 'modal-xl'
  };

  return (
    <Transition appear show={open} as={Fragment}>
      <Dialog as="div" className="modal-overlay" onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter="modal-backdrop-enter"
          enterFrom="modal-backdrop-enter-from"
          enterTo="modal-backdrop-enter-to"
          leave="modal-backdrop-leave"
          leaveFrom="modal-backdrop-leave-from"
          leaveTo="modal-backdrop-leave-to"
        >
          <div className="modal-backdrop" aria-hidden="true" />
        </Transition.Child>

        <div className="modal-container">
          <Transition.Child
            as={Fragment}
            enter="modal-content-enter"
            enterFrom="modal-content-enter-from"
            enterTo="modal-content-enter-to"
            leave="modal-content-leave"
            leaveFrom="modal-content-leave-from"
            leaveTo="modal-content-leave-to"
          >
            <Dialog.Panel className={`modal-panel ${sizeMap[size]}`}>
              {title && (
                <div className="modal-header">
                  <Dialog.Title className="modal-title">{title}</Dialog.Title>
                  <button className="modal-close" onClick={onClose}>
                    <X size={20} />
                  </button>
                </div>
              )}

              <div className="modal-body">
                {children}
              </div>

              {footer && (
                <div className="modal-footer">
                  {footer}
                </div>
              )}
            </Dialog.Panel>
          </Transition.Child>
        </div>
      </Dialog>
    </Transition>
  );
};
