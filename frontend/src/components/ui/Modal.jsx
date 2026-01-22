import { Dialog, Transition } from '@headlessui/react';
import { Fragment } from 'react';
import { X } from '@phosphor-icons/react';
import { Button } from './Button';
import styles from './Modal.module.css';

export function Modal({ 
  isOpen, 
  onClose, 
  title, 
  children,
  footer,
  size = 'md' // sm, md, lg, xl
}) {
  return (
    <Transition appear show={isOpen} as={Fragment}>
      <Dialog as="div" className={styles.dialogOverlay} onClose={onClose}>
        <Transition.Child
          as={Fragment}
          enter={styles.overlayEnter}
          enterFrom={styles.overlayEnterFrom}
          enterTo={styles.overlayEnterTo}
          leave={styles.overlayLeave}
          leaveFrom={styles.overlayLeaveFrom}
          leaveTo={styles.overlayLeaveTo}
        >
          <div className={styles.overlay} />
        </Transition.Child>

        <div className={styles.dialogContainer}>
          <Transition.Child
            as={Fragment}
            enter={styles.panelEnter}
            enterFrom={styles.panelEnterFrom}
            enterTo={styles.panelEnterTo}
            leave={styles.panelLeave}
            leaveFrom={styles.panelLeaveFrom}
            leaveTo={styles.panelLeaveTo}
          >
            <Dialog.Panel className={`${styles.panel} ${styles[size]}`}>
              {/* Header */}
              <div className={styles.header}>
                <Dialog.Title className={styles.title}>
                  {title}
                </Dialog.Title>
                <button onClick={onClose} className={styles.closeBtn}>
                  <X size={18} />
                </button>
              </div>

              {/* Body */}
              <div className={styles.body}>
                {children}
              </div>

              {/* Footer */}
              {footer && (
                <div className={styles.footer}>
                  {footer}
                </div>
              )}
            </Dialog.Panel>
          </Transition.Child>
        </div>
      </Dialog>
    </Transition>
  );
}
