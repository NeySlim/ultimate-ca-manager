import { BoxProps, ElementProps, Factory, StylesApiProps } from '../../core';
import { __ColorPickerProps, ColorPickerStylesNames } from '../ColorPicker';
import { __BaseInputProps, __InputStylesNames, InputVariant } from '../Input';
import { PopoverProps } from '../Popover';
export type ColorInputStylesNames = 'dropdown' | 'eyeDropperButton' | 'eyeDropperIcon' | 'colorPreview' | ColorPickerStylesNames | __InputStylesNames;
export type ColorInputCssVariables = {
    eyeDropperIcon: '--ci-eye-dropper-icon-size';
    colorPreview: '--ci-preview-size';
};
export interface ColorInputProps extends BoxProps, __BaseInputProps, __ColorPickerProps, StylesApiProps<ColorInputFactory>, ElementProps<'input', 'size' | 'onChange' | 'value' | 'defaultValue'> {
    /** If input is not allowed, the user can only pick value with color picker and swatches, `false` by default */
    disallowInput?: boolean;
    /** Determines whether the input value should be reset to the last known valid value when the input loses focus, `true` by default */
    fixOnBlur?: boolean;
    /** Props passed down to the `Popover` component */
    popoverProps?: PopoverProps;
    /** Determines whether the preview color swatch should be displayed in the left section of the input, `true` by default */
    withPreview?: boolean;
    /** Determines whether eye dropper button should be displayed in the right section, `true` by default */
    withEyeDropper?: boolean;
    /** An icon to replace the default eye dropper icon */
    eyeDropperIcon?: React.ReactNode;
    /** Determines whether the dropdown should be closed when one of the color swatches is clicked, `false` by default */
    closeOnColorSwatchClick?: boolean;
    /** Props passed down to the eye dropper button */
    eyeDropperButtonProps?: Record<string, any>;
}
export type ColorInputFactory = Factory<{
    props: ColorInputProps;
    ref: HTMLInputElement;
    stylesNames: ColorInputStylesNames;
    vars: ColorInputCssVariables;
    variant: InputVariant;
}>;
export declare const ColorInput: import("../../core").MantineComponent<{
    props: ColorInputProps;
    ref: HTMLInputElement;
    stylesNames: ColorInputStylesNames;
    vars: ColorInputCssVariables;
    variant: InputVariant;
}>;
