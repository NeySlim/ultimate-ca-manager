import { TransitionStatus } from 'react-transition-group';
import type { NotificationsProps } from './Notifications';
interface NotificationStateStylesProps {
    state: TransitionStatus;
    maxHeight: number | string;
    position: NotificationsProps['position'];
    transitionDuration: number;
}
export declare function getNotificationStateStyles({ state, maxHeight, position, transitionDuration, }: NotificationStateStylesProps): React.CSSProperties;
export {};
