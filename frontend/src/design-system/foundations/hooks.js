import { useEffect, useRef } from 'react';

/**
 * useStaggerAnimation - Anime éléments avec delay progressif
 */
export function useStaggerAnimation(itemCount, delay = 50) {
  const refs = useRef([]);
  
  useEffect(() => {
    refs.current.forEach((el, idx) => {
      if (!el) return;
      el.style.opacity = '0';
      el.style.transform = 'translateY(10px)';
      
      setTimeout(() => {
        el.style.transition = 'all 0.4s ease';
        el.style.opacity = '1';
        el.style.transform = 'translateY(0)';
      }, idx * delay);
    });
  }, [itemCount, delay]);
  
  return refs;
}

/**
 * useFadeIn - Fade in simple sur mount
 */
export function useFadeIn(delay = 0) {
  const ref = useRef(null);
  
  useEffect(() => {
    if (!ref.current) return;
    ref.current.style.opacity = '0';
    
    setTimeout(() => {
      if (ref.current) {
        ref.current.style.transition = 'opacity 0.6s ease';
        ref.current.style.opacity = '1';
      }
    }, delay);
  }, [delay]);
  
  return ref;
}
