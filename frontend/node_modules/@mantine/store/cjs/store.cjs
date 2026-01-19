'use client';
'use strict';

var react = require('react');

function createStore(initialState) {
  let state = initialState;
  let initialized = false;
  const listeners = /* @__PURE__ */ new Set();
  return {
    getState() {
      return state;
    },
    updateState(value) {
      state = typeof value === "function" ? value(state) : value;
    },
    setState(value) {
      this.updateState(value);
      listeners.forEach((listener) => listener(state));
    },
    initialize(value) {
      if (!initialized) {
        state = value;
        initialized = true;
      }
    },
    subscribe(callback) {
      listeners.add(callback);
      return () => listeners.delete(callback);
    }
  };
}
function useStore(store) {
  return react.useSyncExternalStore(
    store.subscribe,
    () => store.getState(),
    () => store.getState()
  );
}

exports.createStore = createStore;
exports.useStore = useStore;
//# sourceMappingURL=store.cjs.map
