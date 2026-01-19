import { NotificationData, NotificationPosition } from '../notifications.store';
export type GroupedNotifications = Record<NotificationPosition, NotificationData[]>;
export declare const positions: NotificationPosition[];
export declare function getGroupedNotifications(notifications: NotificationData[], defaultPosition: NotificationPosition): GroupedNotifications;
