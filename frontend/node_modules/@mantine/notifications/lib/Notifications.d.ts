import { BasePortalProps, BoxProps, ElementProps, Factory, StylesApiProps } from '@mantine/core';
import { NotificationPosition, notifications, NotificationsStore } from './notifications.store';
export type NotificationsStylesNames = 'root' | 'notification';
export type NotificationsCssVariables = {
    root: '--notifications-z-index' | '--notifications-container-width';
};
export interface NotificationsProps extends BoxProps, StylesApiProps<NotificationsFactory>, ElementProps<'div'> {
    /** Notifications default position @default `'bottom-right'` */
    position?: NotificationPosition;
    /** Auto close timeout for all notifications in ms, `false` to disable auto close, can be overwritten for individual notifications in `notifications.show` function @default `4000` */
    autoClose?: number | false;
    /** Notification transition duration in ms @default `250` */
    transitionDuration?: number;
    /** Notification width, cannot exceed 100% @default `440` */
    containerWidth?: number | string;
    /** Notification `max-height`, used for transitions @default `200` */
    notificationMaxHeight?: number | string;
    /** Maximum number of notifications displayed at a time, other new notifications will be added to queue @default `5` */
    limit?: number;
    /** Notifications container z-index @default `400` */
    zIndex?: string | number;
    /** Props passed down to the `Portal` component */
    portalProps?: BasePortalProps;
    /** Store for notifications state, can be used to create multiple instances of notifications system in your application */
    store?: NotificationsStore;
    /** Determines whether notifications container should be rendered inside `Portal` @default `true` */
    withinPortal?: boolean;
}
export type NotificationsFactory = Factory<{
    props: NotificationsProps;
    ref: HTMLDivElement;
    stylesNames: NotificationsStylesNames;
    vars: NotificationsCssVariables;
    staticComponents: {
        show: typeof notifications.show;
        hide: typeof notifications.hide;
        update: typeof notifications.update;
        clean: typeof notifications.clean;
        cleanQueue: typeof notifications.cleanQueue;
        updateState: typeof notifications.updateState;
    };
}>;
export declare const Notifications: import("@mantine/core").MantineComponent<{
    props: NotificationsProps;
    ref: HTMLDivElement;
    stylesNames: NotificationsStylesNames;
    vars: NotificationsCssVariables;
    staticComponents: {
        show: typeof notifications.show;
        hide: typeof notifications.hide;
        update: typeof notifications.update;
        clean: typeof notifications.clean;
        cleanQueue: typeof notifications.cleanQueue;
        updateState: typeof notifications.updateState;
    };
}>;
