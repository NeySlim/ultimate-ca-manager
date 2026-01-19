'use client';
import { jsxs, Fragment, jsx } from 'react/jsx-runtime';
import { Box, Group, Button } from '@mantine/core';
import { useModals } from './use-modals/use-modals.mjs';

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
  const ctx = useModals();
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
  return /* @__PURE__ */ jsxs(Fragment, { children: [
    children && /* @__PURE__ */ jsx(Box, { mb: "md", children }),
    /* @__PURE__ */ jsxs(Group, { mt: children ? 0 : "md", justify: "flex-end", ...groupProps, children: [
      /* @__PURE__ */ jsx(Button, { variant: "default", ...cancelProps, onClick: handleCancel, children: cancelProps?.children || cancelLabel }),
      /* @__PURE__ */ jsx(Button, { ...confirmProps, onClick: handleConfirm, children: confirmProps?.children || confirmLabel })
    ] })
  ] });
}

export { ConfirmModal };
//# sourceMappingURL=ConfirmModal.mjs.map
