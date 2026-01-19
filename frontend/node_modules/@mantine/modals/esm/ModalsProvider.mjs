'use client';
import { jsxs, jsx } from 'react/jsx-runtime';
import { useReducer, useRef, useCallback } from 'react';
import { Modal, getDefaultZIndex } from '@mantine/core';
import { randomId } from '@mantine/hooks';
import { ConfirmModal } from './ConfirmModal.mjs';
import { ModalsContext } from './context.mjs';
import { useModalsEvents } from './events.mjs';
import { modalsReducer } from './reducer.mjs';

function separateConfirmModalProps(props) {
  if (!props) {
    return { confirmProps: {}, modalProps: {} };
  }
  const {
    id,
    children,
    onCancel,
    onConfirm,
    closeOnConfirm,
    closeOnCancel,
    cancelProps,
    confirmProps,
    groupProps,
    labels,
    ...others
  } = props;
  return {
    confirmProps: {
      id,
      children,
      onCancel,
      onConfirm,
      closeOnConfirm,
      closeOnCancel,
      cancelProps,
      confirmProps,
      groupProps,
      labels
    },
    modalProps: {
      id,
      ...others
    }
  };
}
function ModalsProvider({ children, modalProps, labels, modals }) {
  const [state, dispatch] = useReducer(modalsReducer, { modals: [], current: null });
  const stateRef = useRef(state);
  stateRef.current = state;
  const closeAll = useCallback(
    (canceled) => {
      dispatch({ type: "CLOSE_ALL", canceled });
    },
    [stateRef, dispatch]
  );
  const openModal = useCallback(
    ({ modalId, ...props }) => {
      const id = modalId || randomId();
      dispatch({
        type: "OPEN",
        modal: {
          id,
          type: "content",
          props
        }
      });
      return id;
    },
    [dispatch]
  );
  const openConfirmModal = useCallback(
    ({ modalId, ...props }) => {
      const id = modalId || randomId();
      dispatch({
        type: "OPEN",
        modal: {
          id,
          type: "confirm",
          props
        }
      });
      return id;
    },
    [dispatch]
  );
  const openContextModal = useCallback(
    (modal, { modalId, ...props }) => {
      const id = modalId || randomId();
      dispatch({
        type: "OPEN",
        modal: {
          id,
          type: "context",
          props,
          ctx: modal
        }
      });
      return id;
    },
    [dispatch]
  );
  const closeModal = useCallback(
    (id, canceled) => {
      dispatch({ type: "CLOSE", modalId: id, canceled });
    },
    [stateRef, dispatch]
  );
  const updateModal = useCallback(
    ({ modalId, ...newProps }) => {
      dispatch({
        type: "UPDATE",
        modalId,
        newProps
      });
    },
    [dispatch]
  );
  const updateContextModal = useCallback(
    ({ modalId, ...newProps }) => {
      dispatch({ type: "UPDATE", modalId, newProps });
    },
    [dispatch]
  );
  useModalsEvents({
    openModal,
    openConfirmModal,
    openContextModal: ({ modal, ...payload }) => openContextModal(modal, payload),
    closeModal,
    closeContextModal: closeModal,
    closeAllModals: closeAll,
    updateModal,
    updateContextModal
  });
  const ctx = {
    modalProps: modalProps || {},
    modals: state.modals,
    openModal,
    openConfirmModal,
    openContextModal,
    closeModal,
    closeContextModal: closeModal,
    closeAll,
    updateModal,
    updateContextModal
  };
  const getCurrentModal = () => {
    const currentModal = stateRef.current.current;
    switch (currentModal?.type) {
      case "context": {
        const { innerProps, ...rest } = currentModal.props;
        const ContextModal = modals[currentModal.ctx];
        return {
          modalProps: rest,
          content: /* @__PURE__ */ jsx(ContextModal, { innerProps, context: ctx, id: currentModal.id })
        };
      }
      case "confirm": {
        const { modalProps: separatedModalProps, confirmProps: separatedConfirmProps } = separateConfirmModalProps(currentModal.props);
        return {
          modalProps: separatedModalProps,
          content: /* @__PURE__ */ jsx(
            ConfirmModal,
            {
              ...separatedConfirmProps,
              id: currentModal.id,
              labels: currentModal.props.labels || labels
            }
          )
        };
      }
      case "content": {
        const { children: currentModalChildren, ...rest } = currentModal.props;
        return {
          modalProps: rest,
          content: currentModalChildren
        };
      }
      default: {
        return {
          modalProps: {},
          content: null
        };
      }
    }
  };
  const { modalProps: currentModalProps, content } = getCurrentModal();
  return /* @__PURE__ */ jsxs(ModalsContext.Provider, { value: ctx, children: [
    /* @__PURE__ */ jsx(
      Modal,
      {
        zIndex: getDefaultZIndex("modal") + 1,
        ...modalProps,
        ...currentModalProps,
        opened: state.modals.length > 0,
        onClose: () => closeModal(state.current?.id),
        children: content
      }
    ),
    children
  ] });
}

export { ModalsProvider };
//# sourceMappingURL=ModalsProvider.mjs.map
