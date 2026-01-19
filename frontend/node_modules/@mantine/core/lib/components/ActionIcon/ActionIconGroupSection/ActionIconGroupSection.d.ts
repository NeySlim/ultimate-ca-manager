import { BoxProps, ElementProps, Factory, MantineGradient, MantineRadius, MantineSize, StylesApiProps } from '../../../core';
import type { ActionIconVariant } from '../ActionIcon';
export type ActionIconGroupSectionStylesNames = 'groupSection';
export type ActionIconGroupSectionCssVariables = {
    groupSection: '--section-radius' | '--section-bg' | '--section-color' | '--section-bd' | '--section-height' | '--section-padding-x' | '--section-fz';
};
export interface ActionIconGroupSectionProps extends BoxProps, StylesApiProps<ActionIconGroupSectionFactory>, ElementProps<'div'> {
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, `theme.defaultRadius` by default */
    radius?: MantineRadius;
    /** Gradient configuration used when `variant="gradient"`, default value is `theme.defaultGradient` */
    gradient?: MantineGradient;
    /** Determines whether section text color with filled variant should depend on `background-color`. If luminosity of the `color` prop is less than `theme.luminosityThreshold`, then `theme.white` will be used for text color, otherwise `theme.black`. Overrides `theme.autoContrast`. */
    autoContrast?: boolean;
    /** Controls section `height`, `font-size` and horizontal `padding`, `'sm'` by default */
    size?: MantineSize | (string & {}) | number;
}
export type ActionIconGroupSectionFactory = Factory<{
    props: ActionIconGroupSectionProps;
    ref: HTMLDivElement;
    stylesNames: ActionIconGroupSectionStylesNames;
    vars: ActionIconGroupSectionCssVariables;
    variant: ActionIconVariant;
}>;
export declare const ActionIconGroupSection: import("../../../core").MantineComponent<{
    props: ActionIconGroupSectionProps;
    ref: HTMLDivElement;
    stylesNames: ActionIconGroupSectionStylesNames;
    vars: ActionIconGroupSectionCssVariables;
    variant: ActionIconVariant;
}>;
