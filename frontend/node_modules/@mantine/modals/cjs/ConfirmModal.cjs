'use client';
'use strict';

var jsxRuntime = require('react/jsx-runtime');
var core = require('@mantine/core');
var useModals = require('./use-modals/use-modals.cjs');

function ConfirmModal({
  id,
  cancelProps,
  confirmProps,
  labels = { cancel: "", confirm: "" },
  closeOnConfirm = true,
  closeOnCancel = true,
  groupProps,
  onCancel,
  onConfirm,
  children
}) {
  const { cancel: cancelLabel, confirm: confirmLabel } = labels;
  const ctx = useModals.useModals();
  const handleCancel = (event) => {
    typeof cancelProps?.onClick === "function" && cancelProps?.onClick(event);
    typeof onCancel === "function" && onCancel();
    closeOnCancel && ctx.closeModal(id);
  };
  const handleConfirm = (event) => {
    typeof confirmProps?.onClick === "function" && confirmProps?.onClick(event);
    typeof onConfirm === "function" && onConfirm();
    closeOnConfirm && ctx.closeModal(id);
  };
  return /* @__PURE__ */ jsxRuntime.jsxs(jsxRuntime.Fragment, { children: [
    children && /* @__PURE__ */ jsxRuntime.jsx(core.Box, { mb: "md", children }),
    /* @__PURE__ */ jsxRuntime.jsxs(core.Group, { mt: children ? 0 : "md", justify: "flex-end", ...groupProps, children: [
      /* @__PURE__ */ jsxRuntime.jsx(core.Button, { variant: "default", ...cancelProps, onClick: handleCancel, children: cancelProps?.children || cancelLabel }),
      /* @__PURE__ */ jsxRuntime.jsx(core.Button, { ...confirmProps, onClick: handleConfirm, children: confirmProps?.children || confirmLabel })
    ] })
  ] });
}

exports.ConfirmModal = ConfirmModal;
//# sourceMappingURL=ConfirmModal.cjs.map
