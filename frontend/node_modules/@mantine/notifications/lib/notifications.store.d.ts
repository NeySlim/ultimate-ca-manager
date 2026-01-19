import { NotificationProps } from '@mantine/core';
import { MantineStore } from '@mantine/store';
export type NotificationPosition = 'top-left' | 'top-right' | 'top-center' | 'bottom-left' | 'bottom-right' | 'bottom-center';
export interface NotificationData extends Omit<NotificationProps, 'onClose'>, Record<`data-${string}`, any> {
    /** Notification id, can be used to close or update notification */
    id?: string;
    /** Position of the notification, if not set, the position is determined based on `position` prop on Notifications component */
    position?: NotificationPosition;
    /** Notification message, required for all notifications */
    message: React.ReactNode;
    /** Determines whether notification should be closed automatically,
     *  number is auto close timeout in ms, overrides `autoClose` from `Notifications`
     * */
    autoClose?: boolean | number;
    /** Called when notification closes */
    onClose?: (props: NotificationData) => void;
    /** Called when notification opens */
    onOpen?: (props: NotificationData) => void;
}
export interface NotificationsState {
    notifications: NotificationData[];
    queue: NotificationData[];
    defaultPosition: NotificationPosition;
    limit: number;
}
export type NotificationsStore = MantineStore<NotificationsState>;
export declare const createNotificationsStore: () => MantineStore<NotificationsState>;
export declare const notificationsStore: MantineStore<NotificationsState>;
export declare const useNotifications: (store?: NotificationsStore) => NotificationsState;
export declare function updateNotificationsState(store: NotificationsStore, update: (notifications: NotificationData[]) => NotificationData[]): void;
export declare function showNotification(notification: NotificationData, store?: NotificationsStore): string;
export declare function hideNotification(id: string, store?: NotificationsStore): string;
export declare function updateNotification(notification: NotificationData, store?: NotificationsStore): string | undefined;
export declare function cleanNotifications(store?: NotificationsStore): void;
export declare function cleanNotificationsQueue(store?: NotificationsStore): void;
export declare const notifications: {
    readonly show: typeof showNotification;
    readonly hide: typeof hideNotification;
    readonly update: typeof updateNotification;
    readonly clean: typeof cleanNotifications;
    readonly cleanQueue: typeof cleanNotificationsQueue;
    readonly updateState: typeof updateNotificationsState;
};
