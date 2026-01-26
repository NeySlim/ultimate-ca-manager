import { useEffect, useRef, useState } from 'react';

export function usePageTransition() {
  const ref = useRef(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.classList.add('pageTransition');
    }
  }, []);

  return ref;
}

export function useStaggerAnimation() {
  const containerRef = useRef(null);
  const itemClass = 'stagger-item';

  useEffect(() => {
    if (containerRef.current) {
      const items = containerRef.current.querySelectorAll(`.${itemClass}`);
      items.forEach((item, index) => {
        item.style.animationDelay = `${index * 0.05}s`;
      });
    }
  }, []);

  return { containerRef, itemClass };
}

export function useDeleteAnimation() {
  const deleteItem = (element, callback) => {
    if (!element) return;

    element.classList.add('deleteOut');
    element.addEventListener('animationend', () => {
      if (callback) callback();
    }, { once: true });
  };

  return deleteItem;
}

export function useErrorShake() {
  const shake = (element) => {
    if (!element) return;

    element.classList.add('errorShake');
    element.addEventListener('animationend', () => {
      element.classList.remove('errorShake');
    }, { once: true });
  };

  return shake;
}

export function useSuccessPulse() {
  const pulse = (element) => {
    if (!element) return;

    element.classList.add('successPulse');
    element.addEventListener('animationend', () => {
      element.classList.remove('successPulse');
    }, { once: true });
  };

  return pulse;
}

export function useNotificationAnimation() {
  const ref = useRef(null);

  useEffect(() => {
    if (ref.current) {
      ref.current.classList.add('notificationSlideIn');
    }
  }, []);

  return ref;
}

export function useAccordion(initialOpen = false) {
  const [isOpen, setIsOpen] = useState(initialOpen);
  const contentRef = useRef(null);

  useEffect(() => {
    if (contentRef.current) {
      if (isOpen) {
        contentRef.current.classList.remove('accordionCollapse');
        contentRef.current.classList.add('accordionExpand');
      } else {
        contentRef.current.classList.remove('accordionExpand');
        contentRef.current.classList.add('accordionCollapse');
      }
    }
  }, [isOpen]);

  const toggle = () => setIsOpen(!isOpen);

  return { isOpen, toggle, contentRef };
}
