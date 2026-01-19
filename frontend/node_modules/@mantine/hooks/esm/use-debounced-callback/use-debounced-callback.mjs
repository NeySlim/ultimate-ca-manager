'use client';
import { useRef, useCallback, useEffect } from 'react';
import { useCallbackRef } from '../use-callback-ref/use-callback-ref.mjs';

function useDebouncedCallback(callback, options) {
  const delay = typeof options === "number" ? options : options.delay;
  const flushOnUnmount = typeof options === "number" ? false : options.flushOnUnmount;
  const handleCallback = useCallbackRef(callback);
  const debounceTimerRef = useRef(0);
  const flushRef = useRef(() => {
  });
  const lastCallback = Object.assign(
    useCallback(
      (...args) => {
        window.clearTimeout(debounceTimerRef.current);
        const flush = () => {
          if (debounceTimerRef.current !== 0) {
            debounceTimerRef.current = 0;
            handleCallback(...args);
          }
        };
        flushRef.current = flush;
        lastCallback.flush = flush;
        debounceTimerRef.current = window.setTimeout(flush, delay);
      },
      [handleCallback, delay]
    ),
    { flush: flushRef.current }
  );
  useEffect(
    () => () => {
      window.clearTimeout(debounceTimerRef.current);
      if (flushOnUnmount) {
        lastCallback.flush();
      }
    },
    [lastCallback, flushOnUnmount]
  );
  return lastCallback;
}

export { useDebouncedCallback };
//# sourceMappingURL=use-debounced-callback.mjs.map
