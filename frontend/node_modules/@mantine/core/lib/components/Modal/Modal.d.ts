import { Factory } from '../../core';
import { ModalBaseCloseButtonProps, ModalBaseOverlayProps } from '../ModalBase';
import { ModalBody } from './ModalBody';
import { ModalCloseButton } from './ModalCloseButton';
import { ModalContent } from './ModalContent';
import { ModalHeader } from './ModalHeader';
import { ModalOverlay } from './ModalOverlay';
import { ModalRoot, ModalRootCssVariables, ModalRootProps, ModalRootStylesNames } from './ModalRoot';
import { ModalStack } from './ModalStack';
import { ModalTitle } from './ModalTitle';
export type ModalStylesNames = ModalRootStylesNames;
export type ModalCssVariables = ModalRootCssVariables;
export interface ModalProps extends ModalRootProps {
    __staticSelector?: string;
    /** Modal title */
    title?: React.ReactNode;
    /** Determines whether the overlay should be rendered, `true` by default */
    withOverlay?: boolean;
    /** Props passed down to the `Overlay` component, use to configure opacity, `background-color`, styles and other properties */
    overlayProps?: ModalBaseOverlayProps;
    /** Modal content */
    children?: React.ReactNode;
    /** Determines whether the close button should be rendered, `true` by default */
    withCloseButton?: boolean;
    /** Props passed down to the close button */
    closeButtonProps?: ModalBaseCloseButtonProps;
    /** Id of the modal in the `Modal.Stack` */
    stackId?: string;
}
export type ModalFactory = Factory<{
    props: ModalProps;
    ref: HTMLDivElement;
    stylesNames: ModalStylesNames;
    vars: ModalCssVariables;
    staticComponents: {
        Root: typeof ModalRoot;
        Overlay: typeof ModalOverlay;
        Content: typeof ModalContent;
        Body: typeof ModalBody;
        Header: typeof ModalHeader;
        Title: typeof ModalTitle;
        CloseButton: typeof ModalCloseButton;
        Stack: typeof ModalStack;
    };
}>;
export declare const Modal: import("../../core").MantineComponent<{
    props: ModalProps;
    ref: HTMLDivElement;
    stylesNames: ModalStylesNames;
    vars: ModalCssVariables;
    staticComponents: {
        Root: typeof ModalRoot;
        Overlay: typeof ModalOverlay;
        Content: typeof ModalContent;
        Body: typeof ModalBody;
        Header: typeof ModalHeader;
        Title: typeof ModalTitle;
        CloseButton: typeof ModalCloseButton;
        Stack: typeof ModalStack;
    };
}>;
