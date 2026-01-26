import React, { useEffect } from 'react';
import styles from './Confetti.module.css';

export function Confetti({ duration = 3000, onComplete }) {
  useEffect(() => {
    const timer = setTimeout(() => {
      onComplete?.();
    }, duration);
    return () => clearTimeout(timer);
  }, [duration, onComplete]);
  
  return (
    <div className={styles.container}>
      {Array.from({ length: 50 }, (_, i) => (
        <div
          key={i}
          className={styles.confetti}
          style={{
            '--x': `${Math.random() * 100}vw`,
            '--y': `${-20 - Math.random() * 20}px`,
            '--r': `${Math.random() * 360}deg`,
            '--s': `${0.3 + Math.random() * 0.7}`,
            '--delay': `${Math.random() * 0.3}s`,
            '--duration': `${2 + Math.random() * 2}s`,
            '--color': `hsl(${Math.random() * 360}, 70%, 60%)`,
          }}
        />
      ))}
    </div>
  );
}
