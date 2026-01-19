import { Factory, MantineRadius, StylesApiProps } from '../../core';
import { ModalBaseProps, ModalBaseStylesNames } from '../ModalBase';
import { ScrollAreaComponent } from './Modal.context';
export type ModalRootStylesNames = ModalBaseStylesNames;
export type ModalRootCssVariables = {
    root: '--modal-radius' | '--modal-size' | '--modal-y-offset' | '--modal-x-offset';
};
export interface ModalRootProps extends StylesApiProps<ModalRootFactory>, ModalBaseProps {
    __staticSelector?: string;
    /** Top/bottom modal offset, `5dvh` by default */
    yOffset?: React.CSSProperties['marginTop'];
    /** Left/right modal offset, `5vw` by default */
    xOffset?: React.CSSProperties['marginLeft'];
    /** Scroll area component, native `div` element by default */
    scrollAreaComponent?: ScrollAreaComponent;
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, `theme.defaultRadius` by default */
    radius?: MantineRadius;
    /** Determines whether the modal should be centered vertically, `false` by default */
    centered?: boolean;
    /** Determines whether the modal should take the entire screen, `false` by default */
    fullScreen?: boolean;
}
export type ModalRootFactory = Factory<{
    props: ModalRootProps;
    ref: HTMLDivElement;
    stylesNames: ModalRootStylesNames;
    vars: ModalRootCssVariables;
    compound: true;
}>;
export declare const ModalRoot: import("../../core").MantineComponent<{
    props: ModalRootProps;
    ref: HTMLDivElement;
    stylesNames: ModalRootStylesNames;
    vars: ModalRootCssVariables;
    compound: true;
}>;
