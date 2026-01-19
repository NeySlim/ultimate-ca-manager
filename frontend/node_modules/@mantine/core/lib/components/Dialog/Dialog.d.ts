import { BoxProps, ElementProps, Factory, MantineSize, StylesApiProps } from '../../core';
import { AffixBaseProps } from '../Affix';
import { PaperBaseProps } from '../Paper';
import { TransitionOverride } from '../Transition';
export type DialogStylesNames = 'root' | 'closeButton';
export type DialogCssVariables = {
    root: '--dialog-size';
};
export interface DialogProps extends BoxProps, AffixBaseProps, PaperBaseProps, StylesApiProps<DialogFactory>, ElementProps<'div'> {
    /** If set dialog will not be unmounted from the DOM when it is hidden, display: none styles will be added instead */
    keepMounted?: boolean;
    /** Determines whether the close button should be displayed, `true` by default */
    withCloseButton?: boolean;
    /** Called when the close button is clicked */
    onClose?: () => void;
    /** Dialog content */
    children?: React.ReactNode;
    /** Opened state */
    opened: boolean;
    /** Overrides default transition, `{ transition: 'pop-top-right', duration: 200 }` by default */
    transitionProps?: TransitionOverride;
    /** Controls `width` of the dialog, `'md'` by default */
    size?: MantineSize | (string & {}) | number;
}
export type DialogFactory = Factory<{
    props: DialogProps;
    ref: HTMLDivElement;
    stylesNames: DialogStylesNames;
    vars: DialogCssVariables;
}>;
export declare const Dialog: import("../../core").MantineComponent<{
    props: DialogProps;
    ref: HTMLDivElement;
    stylesNames: DialogStylesNames;
    vars: DialogCssVariables;
}>;
