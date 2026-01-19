import { NotificationProps } from '@mantine/core';
import { NotificationData } from './notifications.store';
interface NotificationContainerProps extends NotificationProps {
    data: NotificationData;
    onHide: (id: string) => void;
    autoClose: number | false;
}
export declare const NotificationContainer: import("react").ForwardRefExoticComponent<NotificationContainerProps & import("react").RefAttributes<HTMLDivElement>>;
export {};
