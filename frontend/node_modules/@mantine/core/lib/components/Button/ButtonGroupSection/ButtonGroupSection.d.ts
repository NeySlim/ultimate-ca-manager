import { BoxProps, ElementProps, Factory, MantineGradient, MantineRadius, MantineSize, StylesApiProps } from '../../../core';
import type { ButtonVariant } from '../Button';
export type ButtonGroupSectionStylesNames = 'groupSection';
export type ButtonGroupSectionCssVariables = {
    groupSection: '--section-radius' | '--section-bg' | '--section-color' | '--section-bd' | '--section-height' | '--section-padding-x' | '--section-fz';
};
export interface ButtonGroupSectionProps extends BoxProps, StylesApiProps<ButtonGroupSectionFactory>, ElementProps<'div'> {
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, `theme.defaultRadius` by default */
    radius?: MantineRadius;
    /** Gradient configuration used when `variant="gradient"`, default value is `theme.defaultGradient` */
    gradient?: MantineGradient;
    /** Determines whether section text color with filled variant should depend on `background-color`. If luminosity of the `color` prop is less than `theme.luminosityThreshold`, then `theme.white` will be used for text color, otherwise `theme.black`. Overrides `theme.autoContrast`. */
    autoContrast?: boolean;
    /** Controls section `height`, `font-size` and horizontal `padding`, `'sm'` by default */
    size?: MantineSize | `compact-${MantineSize}` | (string & {});
}
export type ButtonGroupSectionFactory = Factory<{
    props: ButtonGroupSectionProps;
    ref: HTMLDivElement;
    stylesNames: ButtonGroupSectionStylesNames;
    vars: ButtonGroupSectionCssVariables;
    variant: ButtonVariant;
}>;
export declare const ButtonGroupSection: import("../../../core").MantineComponent<{
    props: ButtonGroupSectionProps;
    ref: HTMLDivElement;
    stylesNames: ButtonGroupSectionStylesNames;
    vars: ButtonGroupSectionCssVariables;
    variant: ButtonVariant;
}>;
