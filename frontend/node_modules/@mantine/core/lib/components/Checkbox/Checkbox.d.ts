import { BoxProps, ElementProps, Factory, MantineColor, MantineRadius, MantineSize, StylesApiProps } from '../../core';
import { InlineInputStylesNames } from '../InlineInput';
import { CheckboxCard } from './CheckboxCard/CheckboxCard';
import { CheckboxGroup } from './CheckboxGroup/CheckboxGroup';
import { CheckboxIndicator } from './CheckboxIndicator/CheckboxIndicator';
export type CheckboxVariant = 'filled' | 'outline';
export type CheckboxStylesNames = 'icon' | 'inner' | 'input' | InlineInputStylesNames;
export type CheckboxCssVariables = {
    root: '--checkbox-size' | '--checkbox-radius' | '--checkbox-color' | '--checkbox-icon-color';
};
export interface CheckboxProps extends BoxProps, StylesApiProps<CheckboxFactory>, ElementProps<'input', 'size' | 'children'> {
    /** Id used to connect input with the label. If not set, unique id is generated instead. */
    id?: string;
    /** Content of the `label` associated with the checkbox */
    label?: React.ReactNode;
    /** Key of `theme.colors` or any valid CSS color to set input background color in checked state, `theme.primaryColor` by default */
    color?: MantineColor;
    /** Controls size of the component, `'sm'` by default */
    size?: MantineSize | (string & {});
    /** Key of `theme.radius` or any valid CSS value to set `border-radius,` `theme.defaultRadius` by default */
    radius?: MantineRadius;
    /** Props passed down to the root element */
    wrapperProps?: Record<string, any>;
    /** Position of the label relative to the input, `'right'` by default */
    labelPosition?: 'left' | 'right';
    /** Description displayed below the label */
    description?: React.ReactNode;
    /** Error message displayed below the label */
    error?: React.ReactNode;
    /** Indeterminate state of the checkbox. If set, `checked` prop is ignored. */
    indeterminate?: boolean;
    /** Icon displayed when checkbox is in checked or indeterminate state */
    icon?: React.FC<{
        indeterminate: boolean | undefined;
        className: string;
    }>;
    /** Assigns ref of the root element */
    rootRef?: React.ForwardedRef<HTMLDivElement>;
    /** Key of `theme.colors` or any valid CSS color to set icon color, by default value depends on `theme.autoContrast` */
    iconColor?: MantineColor;
    /** Determines whether icon color with filled variant should depend on `background-color`. If luminosity of the `color` prop is less than `theme.luminosityThreshold`, then `theme.white` will be used for text color, otherwise `theme.black`. Overrides `theme.autoContrast`. */
    autoContrast?: boolean;
}
export type CheckboxFactory = Factory<{
    props: CheckboxProps;
    ref: HTMLInputElement;
    stylesNames: CheckboxStylesNames;
    vars: CheckboxCssVariables;
    variant: CheckboxVariant;
    staticComponents: {
        Group: typeof CheckboxGroup;
        Indicator: typeof CheckboxIndicator;
        Card: typeof CheckboxCard;
    };
}>;
export declare const Checkbox: import("../../core").MantineComponent<{
    props: CheckboxProps;
    ref: HTMLInputElement;
    stylesNames: CheckboxStylesNames;
    vars: CheckboxCssVariables;
    variant: CheckboxVariant;
    staticComponents: {
        Group: typeof CheckboxGroup;
        Indicator: typeof CheckboxIndicator;
        Card: typeof CheckboxCard;
    };
}>;
