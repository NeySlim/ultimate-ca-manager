import { BoxProps, ElementProps, Factory, MantineColor, MantineRadius, MantineSize, StylesApiProps } from '../../core';
import { ChipGroup } from './ChipGroup/ChipGroup';
export type ChipStylesNames = 'root' | 'input' | 'iconWrapper' | 'checkIcon' | 'label';
export type ChipVariant = 'outline' | 'filled' | 'light';
export type ChipCssVariables = {
    root: '--chip-fz' | '--chip-size' | '--chip-icon-size' | '--chip-padding' | '--chip-checked-padding' | '--chip-radius' | '--chip-bg' | '--chip-hover' | '--chip-color' | '--chip-bd' | '--chip-spacing';
};
export interface ChipProps extends BoxProps, StylesApiProps<ChipFactory>, ElementProps<'input', 'size' | 'onChange'> {
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, `'xl'` by default */
    radius?: MantineRadius;
    /** Controls various properties related to component size, `'sm'` by default */
    size?: MantineSize;
    /** Chip input type, `'checkbox'` by default */
    type?: 'radio' | 'checkbox';
    /** `label` element associated with the input */
    children: React.ReactNode;
    /** Checked state for controlled component */
    checked?: boolean;
    /** Default checked state for uncontrolled component */
    defaultChecked?: boolean;
    /** Calls when checked state changes */
    onChange?: (checked: boolean) => void;
    /** Controls components colors based on `variant` prop. Key of `theme.colors` or any valid CSS color. `theme.primaryColor` by default */
    color?: MantineColor;
    /** Static id to connect input with the label, by default `id` is randomly generated */
    id?: string;
    /** Props passed down to the root element */
    wrapperProps?: Record<string, any>;
    /** Any element or component to replace default icon */
    icon?: React.ReactNode;
    /** Assigns ref of the root element */
    rootRef?: React.ForwardedRef<HTMLDivElement>;
    /** Determines whether button text color with filled variant should depend on `background-color`. If luminosity of the `color` prop is less than `theme.luminosityThreshold`, then `theme.white` will be used for text color, otherwise `theme.black`. Overrides `theme.autoContrast`. */
    autoContrast?: boolean;
}
export type ChipFactory = Factory<{
    props: ChipProps;
    ref: HTMLInputElement;
    stylesNames: ChipStylesNames;
    vars: ChipCssVariables;
    variant: ChipVariant;
    staticComponents: {
        Group: typeof ChipGroup;
    };
}>;
export declare const Chip: import("../../core").MantineComponent<{
    props: ChipProps;
    ref: HTMLInputElement;
    stylesNames: ChipStylesNames;
    vars: ChipCssVariables;
    variant: ChipVariant;
    staticComponents: {
        Group: typeof ChipGroup;
    };
}>;
