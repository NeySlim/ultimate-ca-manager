import { BoxProps, ElementProps, Factory, MantineFontSize, StylesApiProps } from '../../../core';
import { InputDescriptionCssVariables, InputDescriptionStylesNames } from '../InputDescription/InputDescription';
import { InputErrorCssVariables, InputErrorStylesNames } from '../InputError/InputError';
import { InputLabelCssVariables, InputLabelStylesNames } from '../InputLabel/InputLabel';
export type InputWrapperCssVariables = InputLabelCssVariables & InputErrorCssVariables & InputDescriptionCssVariables;
export type InputWrapperStylesNames = 'root' | InputLabelStylesNames | InputDescriptionStylesNames | InputErrorStylesNames;
export interface __InputWrapperProps {
    /** Contents of `Input.Label` component. If not set, label is not rendered. */
    label?: React.ReactNode;
    /** Contents of `Input.Description` component. If not set, description is not rendered. */
    description?: React.ReactNode;
    /** Contents of `Input.Error` component. If not set, error is not rendered. */
    error?: React.ReactNode;
    /** Adds required attribute to the input and a red asterisk on the right side of label, `false` by default */
    required?: boolean;
    /** Determines whether the required asterisk should be displayed. Overrides `required` prop. Does not add required attribute to the input. `false` by default */
    withAsterisk?: boolean;
    /** Props passed down to the `Input.Label` component */
    labelProps?: Record<string, any>;
    /** Props passed down to the `Input.Description` component */
    descriptionProps?: Record<string, any>;
    /** Props passed down to the `Input.Error` component */
    errorProps?: Record<string, any>;
    /** Input container component, `React.Fragment` by default */
    inputContainer?: (children: React.ReactNode) => React.ReactNode;
    /** Controls order of the elements, `['label', 'description', 'input', 'error']` by default */
    inputWrapperOrder?: ('label' | 'input' | 'description' | 'error')[];
}
export interface InputWrapperProps extends __InputWrapperProps, BoxProps, StylesApiProps<InputWrapperFactory>, ElementProps<'div'> {
    __staticSelector?: string;
    /** Props passed to Styles API context, replaces Input.Wrapper props */
    __stylesApiProps?: Record<string, any>;
    /** Static id used as base to generate `aria-` attributes, by default generates random id */
    id?: string;
    /** Controls size of `Input.Label`, `Input.Description` and `Input.Error` components */
    size?: MantineFontSize;
    /** `Input.Label` root element, `'label'` by default */
    labelElement?: 'label' | 'div';
}
export type InputWrapperFactory = Factory<{
    props: InputWrapperProps;
    ref: HTMLDivElement;
    stylesNames: InputWrapperStylesNames;
    vars: InputWrapperCssVariables;
}>;
export declare const InputWrapper: import("../../../core").MantineComponent<{
    props: InputWrapperProps;
    ref: HTMLDivElement;
    stylesNames: InputWrapperStylesNames;
    vars: InputWrapperCssVariables;
}>;
