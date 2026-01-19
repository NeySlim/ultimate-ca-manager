import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../../core';
export type InputPlaceholderStylesNames = 'placeholder';
export interface InputPlaceholderProps extends BoxProps, StylesApiProps<InputPlaceholderFactory>, ElementProps<'span'> {
    __staticSelector?: string;
    /** If set, the placeholder will have error styles, `false` by default */
    error?: React.ReactNode;
}
export type InputPlaceholderFactory = Factory<{
    props: InputPlaceholderProps;
    ref: HTMLSpanElement;
    stylesNames: InputPlaceholderStylesNames;
}>;
export declare const InputPlaceholder: import("../../../core").MantineComponent<{
    props: InputPlaceholderProps;
    ref: HTMLSpanElement;
    stylesNames: InputPlaceholderStylesNames;
}>;
