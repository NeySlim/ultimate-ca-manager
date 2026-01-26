import React, { useEffect, useState } from 'react';
import styles from './AnimatedCounter.module.css';

export const AnimatedCounter = ({ 
  value = 0,
  duration = 1000,
  prefix = '',
  suffix = '',
  decimals = 0,
  className = ''
}) => {
  const [count, setCount] = useState(0);

  useEffect(() => {
    let startTime;
    let animationFrame;

    const animate = (timestamp) => {
      if (!startTime) startTime = timestamp;
      const progress = Math.min((timestamp - startTime) / duration, 1);
      
      const easeOutQuart = 1 - Math.pow(1 - progress, 4);
      setCount(Math.floor(value * easeOutQuart));

      if (progress < 1) {
        animationFrame = requestAnimationFrame(animate);
      }
    };

    animationFrame = requestAnimationFrame(animate);

    return () => cancelAnimationFrame(animationFrame);
  }, [value, duration]);

  const formattedValue = decimals > 0 
    ? count.toFixed(decimals) 
    : count.toLocaleString();

  return (
    <span className={`${styles.counter} ${className}`}>
      {prefix}{formattedValue}{suffix}
    </span>
  );
};

export default AnimatedCounter;
