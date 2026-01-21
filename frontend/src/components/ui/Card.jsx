import { classNames } from '../../utils/classNames';
import styles from './Card.module.css';

/**
 * Card Component
 * 
 * Usage:
 *   <Card>
 *     <Card.Header title="Title" />
 *     <Card.Body>Content</Card.Body>
 *   </Card>
 */
export function Card({ children, className, ...props }) {
  return (
    <div className={classNames(styles.card, className)} {...props}>
      {children}
    </div>
  );
}

Card.Header = function CardHeader({ title, action, className, children, ...props }) {
  return (
    <div className={classNames(styles.cardHeader, className)} {...props}>
      {title && <h3 className={styles.cardTitle}>{title}</h3>}
      {children}
      {action && <div className={styles.cardAction}>{action}</div>}
    </div>
  );
};

Card.Body = function CardBody({ children, className, ...props }) {
  return (
    <div className={classNames(styles.cardBody, className)} {...props}>
      {children}
    </div>
  );
};

export default Card;
