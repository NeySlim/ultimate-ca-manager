import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../core';
import { __BaseInputProps, __InputStylesNames } from '../Input';
export interface TextareaProps extends BoxProps, __BaseInputProps, StylesApiProps<TextareaFactory>, ElementProps<'textarea', 'size'> {
    __staticSelector?: string;
    /** Determines whether the textarea height should grow with its content, `false` by default */
    autosize?: boolean;
    /** Maximum rows for autosize textarea to grow, ignored if `autosize` prop is not set */
    maxRows?: number;
    /** Minimum rows of autosize textarea, ignored if `autosize` prop is not set */
    minRows?: number;
    /** Controls `resize` CSS property, `'none'` by default */
    resize?: React.CSSProperties['resize'];
}
export type TextareaFactory = Factory<{
    props: TextareaProps;
    ref: HTMLTextAreaElement;
    stylesNames: __InputStylesNames;
}>;
export declare const Textarea: import("../../core").MantineComponent<{
    props: TextareaProps;
    ref: HTMLTextAreaElement;
    stylesNames: __InputStylesNames;
}>;
