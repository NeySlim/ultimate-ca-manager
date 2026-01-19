import { BoxProps, ElementProps, Factory, MantineRadius, MantineSize, MantineSpacing, StylesApiProps } from '../../core';
import { InputProps } from '../Input';
export type PinInputStylesNames = 'root' | 'pinInput' | 'input';
export type PinInputCssVariables = {
    root: '--pin-input-size';
};
export interface PinInputProps extends BoxProps, StylesApiProps<PinInputFactory>, ElementProps<'div', 'onChange'> {
    /** Hidden input `name` attribute */
    name?: string;
    /** Hidden input `form` attribute */
    form?: string;
    /** Key of `theme.spacing` or any valid CSS value to set `gap` between inputs, numbers are converted to rem, `'md'` by default */
    gap?: MantineSpacing;
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, numbers are converted to rem, `theme.defaultRadius` by default */
    radius?: MantineRadius;
    /** Controls inputs `width` and `height`, `'sm'` by default */
    size?: MantineSize;
    /** If set, the first input is focused when component is mounted, `false` by default */
    autoFocus?: boolean;
    /** Controlled component value */
    value?: string;
    /** Uncontrolled component default value */
    defaultValue?: string;
    /** Called when value changes */
    onChange?: (value: string) => void;
    /** Called when all inputs have value */
    onComplete?: (value: string) => void;
    /** Inputs placeholder, `'○'` by default */
    placeholder?: string;
    /** Determines whether focus should be moved automatically to the next input once filled, `true` by default */
    manageFocus?: boolean;
    /** Determines whether `autocomplete="one-time-code"` attribute should be set on all inputs, `true` by default */
    oneTimeCode?: boolean;
    /** Base id used for all inputs. By default, inputs' ids are generated randomly. */
    id?: string;
    /** If set, `disabled` attribute is added to all inputs */
    disabled?: boolean;
    /** If set, adds error styles and `aria-invalid` attribute to all inputs */
    error?: boolean;
    /** Determines which values can be entered, `'alphanumeric'` by default */
    type?: 'alphanumeric' | 'number' | RegExp;
    /** Changes input type to `"password"`, `false` by default */
    mask?: boolean;
    /** Number of inputs, `4` by default */
    length?: number;
    /** If set, the user cannot edit the value */
    readOnly?: boolean;
    /** Inputs `type` attribute, inferred from the `type` prop if not specified */
    inputType?: React.HTMLInputTypeAttribute;
    /** `inputmode` attribute, inferred from the `type` prop if not specified */
    inputMode?: 'none' | 'text' | 'tel' | 'url' | 'email' | 'numeric' | 'decimal' | 'search' | undefined;
    /** `aria-label` for the inputs */
    ariaLabel?: string;
    /** Props passed down to the hidden input */
    hiddenInputProps?: React.ComponentPropsWithoutRef<'input'>;
    /** Assigns ref of the root element */
    rootRef?: React.ForwardedRef<HTMLDivElement>;
    /** Props added to the input element depending on its index */
    getInputProps?: (index: number) => InputProps & ElementProps<'input', 'size'>;
}
export type PinInputFactory = Factory<{
    props: PinInputProps;
    ref: HTMLInputElement;
    stylesNames: PinInputStylesNames;
    vars: PinInputCssVariables;
}>;
export declare const PinInput: import("../../core").MantineComponent<{
    props: PinInputProps;
    ref: HTMLInputElement;
    stylesNames: PinInputStylesNames;
    vars: PinInputCssVariables;
}>;
