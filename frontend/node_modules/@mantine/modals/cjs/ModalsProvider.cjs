'use client';
'use strict';

var jsxRuntime = require('react/jsx-runtime');
var react = require('react');
var core = require('@mantine/core');
var hooks = require('@mantine/hooks');
var ConfirmModal = require('./ConfirmModal.cjs');
var context = require('./context.cjs');
var events = require('./events.cjs');
var reducer = require('./reducer.cjs');

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
  const [state, dispatch] = react.useReducer(reducer.modalsReducer, { modals: [], current: null });
  const stateRef = react.useRef(state);
  stateRef.current = state;
  const closeAll = react.useCallback(
    (canceled) => {
      dispatch({ type: "CLOSE_ALL", canceled });
    },
    [stateRef, dispatch]
  );
  const openModal = react.useCallback(
    ({ modalId, ...props }) => {
      const id = modalId || hooks.randomId();
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
  const openConfirmModal = react.useCallback(
    ({ modalId, ...props }) => {
      const id = modalId || hooks.randomId();
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
  const openContextModal = react.useCallback(
    (modal, { modalId, ...props }) => {
      const id = modalId || hooks.randomId();
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
  const closeModal = react.useCallback(
    (id, canceled) => {
      dispatch({ type: "CLOSE", modalId: id, canceled });
    },
    [stateRef, dispatch]
  );
  const updateModal = react.useCallback(
    ({ modalId, ...newProps }) => {
      dispatch({
        type: "UPDATE",
        modalId,
        newProps
      });
    },
    [dispatch]
  );
  const updateContextModal = react.useCallback(
    ({ modalId, ...newProps }) => {
      dispatch({ type: "UPDATE", modalId, newProps });
    },
    [dispatch]
  );
  events.useModalsEvents({
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
          content: /* @__PURE__ */ jsxRuntime.jsx(ContextModal, { innerProps, context: ctx, id: currentModal.id })
        };
      }
      case "confirm": {
        const { modalProps: separatedModalProps, confirmProps: separatedConfirmProps } = separateConfirmModalProps(currentModal.props);
        return {
          modalProps: separatedModalProps,
          content: /* @__PURE__ */ jsxRuntime.jsx(
            ConfirmModal.ConfirmModal,
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
  return /* @__PURE__ */ jsxRuntime.jsxs(context.ModalsContext.Provider, { value: ctx, children: [
    /* @__PURE__ */ jsxRuntime.jsx(
      core.Modal,
      {
        zIndex: core.getDefaultZIndex("modal") + 1,
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

exports.ModalsProvider = ModalsProvider;
//# sourceMappingURL=ModalsProvider.cjs.map
