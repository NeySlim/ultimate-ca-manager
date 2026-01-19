import { BoxProps, ElementProps, Factory, MantineColor, MantineRadius, MantineSize, StylesApiProps } from '../../core';
import { InlineInputStylesNames } from '../InlineInput';
import { RadioCard } from './RadioCard/RadioCard';
import { RadioGroup } from './RadioGroup/RadioGroup';
import { RadioIconProps } from './RadioIcon';
import { RadioIndicator } from './RadioIndicator/RadioIndicator';
export type RadioVariant = 'filled' | 'outline';
export type RadioStylesNames = InlineInputStylesNames | 'inner' | 'radio' | 'icon';
export type RadioCssVariables = {
    root: '--radio-size' | '--radio-radius' | '--radio-color' | '--radio-icon-color' | '--radio-icon-size';
};
export interface RadioProps extends BoxProps, StylesApiProps<RadioFactory>, ElementProps<'input', 'size' | 'children'> {
    /** Content of the `label` associated with the radio */
    label?: React.ReactNode;
    /** Key of `theme.colors` or any valid CSS color to set input color in checked state, `theme.primaryColor` by default */
    color?: MantineColor;
    /** Controls size of the component, `'sm'` by default */
    size?: MantineSize | (string & {});
    /** A component that replaces default check icon */
    icon?: React.FC<RadioIconProps>;
    /** Props passed down to the root element */
    wrapperProps?: Record<string, any>;
    /** Position of the label relative to the input, `'right'` by default */
    labelPosition?: 'left' | 'right';
    /** Description displayed below the label */
    description?: React.ReactNode;
    /** Error displayed below the label */
    error?: React.ReactNode;
    /** Key of `theme.radius` or any valid CSS value to set `border-radius,` "xl" by default */
    radius?: MantineRadius;
    /** Assigns ref of the root element */
    rootRef?: React.ForwardedRef<HTMLDivElement>;
    /** Key of `theme.colors` or any valid CSS color to set icon color, by default value depends on `theme.autoContrast` */
    iconColor?: MantineColor;
    /** Determines whether icon color with filled variant should depend on `background-color`. If luminosity of the `color` prop is less than `theme.luminosityThreshold`, then `theme.white` will be used for text color, otherwise `theme.black`. Overrides `theme.autoContrast`. */
    autoContrast?: boolean;
}
export type RadioFactory = Factory<{
    props: RadioProps;
    ref: HTMLInputElement;
    stylesNames: RadioStylesNames;
    vars: RadioCssVariables;
    variant: RadioVariant;
    staticComponents: {
        Group: typeof RadioGroup;
        Card: typeof RadioCard;
        Indicator: typeof RadioIndicator;
    };
}>;
export declare const Radio: import("../../core").MantineComponent<{
    props: RadioProps;
    ref: HTMLInputElement;
    stylesNames: RadioStylesNames;
    vars: RadioCssVariables;
    variant: RadioVariant;
    staticComponents: {
        Group: typeof RadioGroup;
        Card: typeof RadioCard;
        Indicator: typeof RadioIndicator;
    };
}>;
