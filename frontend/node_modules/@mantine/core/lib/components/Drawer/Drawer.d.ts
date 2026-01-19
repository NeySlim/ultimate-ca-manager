import { Factory } from '../../core';
import { ModalBaseCloseButtonProps, ModalBaseOverlayProps } from '../ModalBase';
import { DrawerBody } from './DrawerBody';
import { DrawerCloseButton } from './DrawerCloseButton';
import { DrawerContent } from './DrawerContent';
import { DrawerHeader } from './DrawerHeader';
import { DrawerOverlay } from './DrawerOverlay';
import { DrawerRoot, DrawerRootCssVariables, DrawerRootProps, DrawerRootStylesNames } from './DrawerRoot';
import { DrawerStack } from './DrawerStack';
import { DrawerTitle } from './DrawerTitle';
export type DrawerStylesNames = DrawerRootStylesNames;
export type DrawerCssVariables = DrawerRootCssVariables;
export interface DrawerProps extends DrawerRootProps {
    /** Drawer title */
    title?: React.ReactNode;
    /** Determines whether the overlay should be rendered, `true` by default */
    withOverlay?: boolean;
    /** Props passed down to the `Overlay` component, can be used to configure opacity, `background-color`, styles and other properties */
    overlayProps?: ModalBaseOverlayProps;
    /** Drawer content */
    children?: React.ReactNode;
    /** Determines whether the close button should be rendered, `true` by default */
    withCloseButton?: boolean;
    /** Props passed down to the close button */
    closeButtonProps?: ModalBaseCloseButtonProps;
    /** Id of the drawer in the `Drawer.Stack` */
    stackId?: string;
}
export type DrawerFactory = Factory<{
    props: DrawerProps;
    ref: HTMLDivElement;
    stylesNames: DrawerStylesNames;
    vars: DrawerCssVariables;
    staticComponents: {
        Root: typeof DrawerRoot;
        Overlay: typeof DrawerOverlay;
        Content: typeof DrawerContent;
        Body: typeof DrawerBody;
        Header: typeof DrawerHeader;
        Title: typeof DrawerTitle;
        CloseButton: typeof DrawerCloseButton;
        Stack: typeof DrawerStack;
    };
}>;
export declare const Drawer: import("../../core").MantineComponent<{
    props: DrawerProps;
    ref: HTMLDivElement;
    stylesNames: DrawerStylesNames;
    vars: DrawerCssVariables;
    staticComponents: {
        Root: typeof DrawerRoot;
        Overlay: typeof DrawerOverlay;
        Content: typeof DrawerContent;
        Body: typeof DrawerBody;
        Header: typeof DrawerHeader;
        Title: typeof DrawerTitle;
        CloseButton: typeof DrawerCloseButton;
        Stack: typeof DrawerStack;
    };
}>;
