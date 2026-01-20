import React from 'react';
import './Layout.css';

/**
 * Stack - Vertical layout (replaces Mantine Stack)
 */
export const Stack = ({ 
  children, 
  gap = 'md',
  align = 'stretch',
  className = '',
  ...props
}) => {
  const gapMap = {
    xs: 'gap-xs',
    sm: 'gap-sm',
    md: 'gap-md',
    lg: 'gap-lg',
    xl: 'gap-xl'
  };

  const classes = ['stack', gapMap[gap], `align-${align}`, className]
    .filter(Boolean)
    .join(' ');

  return <div className={classes} {...props}>{children}</div>;
};

/**
 * Group - Horizontal layout (replaces Mantine Group)
 */
export const Group = ({ 
  children, 
  gap = 'md',
  align = 'center',
  justify = 'flex-start',
  className = '',
  wrap = false,
  ...props
}) => {
  const gapMap = {
    xs: 'gap-xs',
    sm: 'gap-sm',
    md: 'gap-md',
    lg: 'gap-lg',
    xl: 'gap-xl'
  };

  const classes = [
    'group',
    gapMap[gap],
    `align-${align}`,
    `justify-${justify}`,
    wrap && 'wrap',
    className
  ].filter(Boolean).join(' ');

  return <div className={classes} {...props}>{children}</div>;
};

/**
 * Card - Container component (replaces Mantine Paper/Card)
 */
export const Card = ({ 
  children,
  padding = 'md',
  className = '',
  withBorder = true,
  ...props
}) => {
  const paddingMap = {
    xs: 'p-xs',
    sm: 'p-sm',
    md: 'p-md',
    lg: 'p-lg',
    xl: 'p-xl',
    0: 'p-0'
  };

  const classes = [
    'card',
    paddingMap[padding],
    withBorder ? '' : 'no-border',
    className
  ].filter(Boolean).join(' ');

  return <div className={classes} {...props}>{children}</div>;
};

/**
 * Divider - Separator line
 */
export const Divider = ({ 
  orientation = 'horizontal',
  className = '',
  ...props
}) => {
  const classes = [
    'divider',
    `divider-${orientation}`,
    className
  ].filter(Boolean).join(' ');

  return <hr className={classes} {...props} />;
};
