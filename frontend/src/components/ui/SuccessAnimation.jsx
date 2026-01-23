import React, { useState, useEffect } from 'react';
import styles from './SuccessAnimation.module.css';

export const SuccessAnimation = ({ 
  size = 80,
  message = 'Success!',
  duration = 2000,
  onComplete,
  className = ''
}) => {
  const [visible, setVisible] = useState(true);

  useEffect(() => {
    if (duration > 0) {
      const timer = setTimeout(() => {
        setVisible(false);
        onComplete?.();
      }, duration);
      return () => clearTimeout(timer);
    }
  }, [duration, onComplete]);

  if (!visible) return null;

  return (
    <div className={`${styles.container} ${className}`}>
      <svg className={styles.checkmark} width={size} height={size} viewBox="0 0 52 52">
        <circle className={styles.circle} cx="26" cy="26" r="25" fill="none"/>
        <path className={styles.check} fill="none" d="M14.1 27.2l7.1 7.2 16.7-16.8"/>
      </svg>
      {message && <p className={styles.message}>{message}</p>}
    </div>
  );
};

export const ConfettiEffect = ({ duration = 3000 }) => {
  const [confetti, setConfetti] = useState([]);

  useEffect(() => {
    const pieces = Array.from({ length: 50 }, (_, i) => ({
      id: i,
      left: Math.random() * 100,
      delay: Math.random() * 0.5,
      color: ['#81c784', '#64b5f6', '#ffb74d', '#e57373'][Math.floor(Math.random() * 4)]
    }));
    setConfetti(pieces);

    const timer = setTimeout(() => setConfetti([]), duration);
    return () => clearTimeout(timer);
  }, [duration]);

  return (
    <div className={styles.confettiContainer}>
      {confetti.map(piece => (
        <div
          key={piece.id}
          className={styles.confetti}
          style={{
            left: `${piece.left}%`,
            animationDelay: `${piece.delay}s`,
            backgroundColor: piece.color
          }}
        />
      ))}
    </div>
  );
};

export default SuccessAnimation;
