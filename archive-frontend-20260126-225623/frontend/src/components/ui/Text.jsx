import React from 'react';

/**
 * Text component - Replaces Mantine Text
 * Uses semantic HTML + CSS classes
 */
export const Text = ({ 
  children,
  size = 'sm',
  weight = 'normal',
  color = 'primary',
  align = 'left',
  transform,
  className = '',
  component: Component = 'span',
  ...props
}) => {
  const sizeMap = {
    xs: 'text-xs',
    sm: 'text-sm',
    md: 'text-md',
    lg: 'text-lg',
    xl: 'text-xl'
  };

  const weightMap = {
    normal: '',
    500: 'fw-500',
    600: 'fw-600',
    700: 'fw-700',
    bold: 'fw-bold'
  };

  const colorMap = {
    primary: 'text-primary',
    secondary: 'text-secondary',
    tertiary: 'text-tertiary',
    dimmed: 'text-tertiary',
    muted: 'text-muted'
  };

  const alignMap = {
    left: '',
    center: 'ta-center',
    right: 'ta-right'
  };

  const transformMap = {
    uppercase: 'tt-uppercase',
    lowercase: 'tt-lowercase',
    capitalize: 'tt-capitalize'
  };

  const classes = [
    sizeMap[size],
    weightMap[weight],
    colorMap[color],
    alignMap[align],
    transform && transformMap[transform],
    className
  ].filter(Boolean).join(' ');

  return <Component className={classes} {...props}>{children}</Component>;
};
