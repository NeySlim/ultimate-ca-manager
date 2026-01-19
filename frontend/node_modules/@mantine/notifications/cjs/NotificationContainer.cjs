'use client';
'use strict';

var jsxRuntime = require('react/jsx-runtime');
var react = require('react');
var core = require('@mantine/core');
var getAutoClose = require('./get-auto-close/get-auto-close.cjs');

const NotificationContainer = react.forwardRef(
  ({ data, onHide, autoClose, ...others }, ref) => {
    const { autoClose: _autoClose, message, ...notificationProps } = data;
    const autoCloseDuration = getAutoClose.getAutoClose(autoClose, data.autoClose);
    const autoCloseTimeout = react.useRef(-1);
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
    react.useEffect(() => {
      data.onOpen?.(data);
    }, []);
    react.useEffect(() => {
      handleAutoClose();
      return cancelAutoClose;
    }, [autoCloseDuration]);
    return /* @__PURE__ */ jsxRuntime.jsx(
      core.Notification,
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

exports.NotificationContainer = NotificationContainer;
//# sourceMappingURL=NotificationContainer.cjs.map
