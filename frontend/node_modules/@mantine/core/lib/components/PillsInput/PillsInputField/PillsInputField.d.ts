import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../../core';
export type PillsInputFieldStylesNames = 'field';
export interface PillsInputFieldProps extends BoxProps, StylesApiProps<PillsInputFieldFactory>, ElementProps<'input', 'type'> {
    /** Controls input styles when focused. If `auto` the input is hidden when not focused. If `visible` the input will always remain visible. `'visible'` by default  */
    type?: 'auto' | 'visible' | 'hidden';
    /** If set, cursor is changed to pointer */
    pointer?: boolean;
}
export type PillsInputFieldFactory = Factory<{
    props: PillsInputFieldProps;
    ref: HTMLInputElement;
    stylesNames: PillsInputFieldStylesNames;
}>;
export declare const PillsInputField: import("../../../core").MantineComponent<{
    props: PillsInputFieldProps;
    ref: HTMLInputElement;
    stylesNames: PillsInputFieldStylesNames;
}>;
