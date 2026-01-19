import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../core';
import { __BaseInputProps, __InputStylesNames, InputVariant } from '../Input';
export type PasswordInputStylesNames = 'root' | 'visibilityToggle' | 'innerInput' | __InputStylesNames;
export type PasswordInputCssVariables = {
    root: '--psi-icon-size' | '--psi-button-size';
};
export interface PasswordInputProps extends BoxProps, __BaseInputProps, StylesApiProps<PasswordInputFactory>, ElementProps<'input', 'size'> {
    /** A component to replace visibility toggle icon */
    visibilityToggleIcon?: React.FC<{
        reveal: boolean;
    }>;
    /** Props passed down to the visibility toggle button */
    visibilityToggleButtonProps?: Record<string, any>;
    /** Determines whether input content should be visible */
    visible?: boolean;
    /** Determines whether input content should be visible by default */
    defaultVisible?: boolean;
    /** Called when visibility changes */
    onVisibilityChange?: (visible: boolean) => void;
}
export type PasswordInputFactory = Factory<{
    props: PasswordInputProps;
    ref: HTMLInputElement;
    stylesNames: PasswordInputStylesNames;
    vars: PasswordInputCssVariables;
    variant: InputVariant;
}>;
export declare const PasswordInput: import("../../core").MantineComponent<{
    props: PasswordInputProps;
    ref: HTMLInputElement;
    stylesNames: PasswordInputStylesNames;
    vars: PasswordInputCssVariables;
    variant: InputVariant;
}>;
