'use client';
'use strict';

var React = require('react');
var useCallbackRef = require('../utils/use-callback-ref/use-callback-ref.cjs');

function containsRelatedTarget(event) {
  if (event.currentTarget instanceof HTMLElement && event.relatedTarget instanceof HTMLElement) {
    return event.currentTarget.contains(event.relatedTarget);
  }
  return false;
}
function useFocusWithin({
  onBlur,
  onFocus
} = {}) {
  const [focused, setFocused] = React.useState(false);
  const focusedRef = React.useRef(false);
  const previousNode = React.useRef(null);
  const onFocusRef = useCallbackRef.useCallbackRef(onFocus);
  const onBlurRef = useCallbackRef.useCallbackRef(onBlur);
  const _setFocused = React.useCallback((value) => {
    setFocused(value);
    focusedRef.current = value;
  }, []);
  const handleFocusIn = React.useCallback((event) => {
    if (!focusedRef.current) {
      _setFocused(true);
      onFocusRef(event);
    }
  }, []);
  const handleFocusOut = React.useCallback((event) => {
    if (focusedRef.current && !containsRelatedTarget(event)) {
      _setFocused(false);
      onBlurRef(event);
    }
  }, []);
  const callbackRef = React.useCallback(
    (node) => {
      if (!node) {
        return;
      }
      if (previousNode.current) {
        previousNode.current.removeEventListener("focusin", handleFocusIn);
        previousNode.current.removeEventListener("focusout", handleFocusOut);
      }
      node.addEventListener("focusin", handleFocusIn);
      node.addEventListener("focusout", handleFocusOut);
      previousNode.current = node;
    },
    [handleFocusIn, handleFocusOut]
  );
  React.useEffect(
    () => () => {
      if (previousNode.current) {
        previousNode.current.removeEventListener("focusin", handleFocusIn);
        previousNode.current.removeEventListener("focusout", handleFocusOut);
      }
    },
    []
  );
  return { ref: callbackRef, focused };
}

exports.useFocusWithin = useFocusWithin;
//# sourceMappingURL=use-focus-within.cjs.map
