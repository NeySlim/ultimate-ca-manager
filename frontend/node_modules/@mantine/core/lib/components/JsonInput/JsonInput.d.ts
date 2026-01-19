import { Factory } from '../../core';
import { __InputStylesNames } from '../Input';
import { TextareaProps } from '../Textarea';
export interface JsonInputProps extends Omit<TextareaProps, 'onChange'> {
    /** Value for controlled component */
    value?: string;
    /** Default value for uncontrolled component */
    defaultValue?: string;
    /** Called when value changes */
    onChange?: (value: string) => void;
    /** Determines whether the value should be formatted on blur, `false` by default */
    formatOnBlur?: boolean;
    /** Error message displayed when value is not valid JSON */
    validationError?: React.ReactNode;
    /** Function to serialize value into a string, used for value formatting, `JSON.stringify` by default */
    serialize?: typeof JSON.stringify;
    /** Function to deserialize string value, used for value formatting and input JSON validation, must throw error if string cannot be processed, `JSON.parse` by default */
    deserialize?: typeof JSON.parse;
}
export type JsonInputFactory = Factory<{
    props: JsonInputProps;
    ref: HTMLTextAreaElement;
    stylesNames: __InputStylesNames;
}>;
export declare const JsonInput: import("../../core").MantineComponent<{
    props: JsonInputProps;
    ref: HTMLTextAreaElement;
    stylesNames: __InputStylesNames;
}>;
