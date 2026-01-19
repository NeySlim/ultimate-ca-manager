'use client';
import { jsx } from 'react/jsx-runtime';
import { forwardRef, useRef, useEffect } from 'react';
import { Notification } from '@mantine/core';
import { getAutoClose } from './get-auto-close/get-auto-close.mjs';

const NotificationContainer = forwardRef(
  ({ data, onHide, autoClose, ...others }, ref) => {
    const { autoClose: _autoClose, message, ...notificationProps } = data;
    const autoCloseDuration = getAutoClose(autoClose, data.autoClose);
    const autoCloseTimeout = useRef(-1);
    const cancelAutoClose = () => window.clearTimeout(autoCloseTimeout.current);
    const handleHide = () => {
      onHide(data.id);
      cancelAutoClose();
    };
    const handleAutoClose = () => {
      if (typeof autoCloseDuration === "number") {
        autoCloseTimeout.current = window.setTimeout(handleHide, autoCloseDuration);
      }
    };
    useEffect(() => {
      data.onOpen?.(data);
    }, []);
    useEffect(() => {
      handleAutoClose();
      return cancelAutoClose;
    }, [autoCloseDuration]);
    return /* @__PURE__ */ jsx(
      Notification,
      {
        ...others,
        ...notificationProps,
        onClose: handleHide,
        ref,
        onMouseEnter: cancelAutoClose,
        onMouseLeave: handleAutoClose,
        children: message
      }
    );
  }
);
NotificationContainer.displayName = "@mantine/notifications/NotificationContainer";

export { NotificationContainer };
//# sourceMappingURL=NotificationContainer.mjs.map
