'use client';
function handleCloseModal(modal, canceled) {
  if (canceled && modal.type === "confirm") {
    modal.props.onCancel?.();
  }
  modal.props.onClose?.();
}
function modalsReducer(state, action) {
  switch (action.type) {
    case "OPEN": {
      return {
        current: action.modal,
        modals: [...state.modals, action.modal]
      };
    }
    case "CLOSE": {
      const modal = state.modals.find((m) => m.id === action.modalId);
      if (!modal) {
        return state;
      }
      handleCloseModal(modal, action.canceled);
      const remainingModals = state.modals.filter((m) => m.id !== action.modalId);
      return {
        current: remainingModals[remainingModals.length - 1] || state.current,
        modals: remainingModals
      };
    }
    case "CLOSE_ALL": {
      if (!state.modals.length) {
        return state;
      }
      state.modals.concat().reverse().forEach((modal) => {
        handleCloseModal(modal, action.canceled);
      });
      return {
        current: state.current,
        modals: []
      };
    }
    case "UPDATE": {
      const { modalId, newProps } = action;
      const updatedModals = state.modals.map((modal) => {
        if (modal.id !== modalId) {
          return modal;
        }
        if (modal.type === "content" || modal.type === "confirm") {
          return {
            ...modal,
            props: {
              ...modal.props,
              ...newProps
            }
          };
        }
        if (modal.type === "context") {
          return {
            ...modal,
            props: {
              ...modal.props,
              ...newProps,
              innerProps: {
                ...modal.props.innerProps,
                ...newProps.innerProps
              }
            }
          };
        }
        return modal;
      });
      const currentModal = state.current?.id === modalId ? updatedModals.find((modal) => modal.id === modalId) || state.current : state.current;
      return {
        ...state,
        modals: updatedModals,
        current: currentModal
      };
    }
    default: {
      return state;
    }
  }
}

export { modalsReducer };
//# sourceMappingURL=reducer.mjs.map
