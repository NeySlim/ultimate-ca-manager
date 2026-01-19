import { BoxProps, MantineColor, MantineGradient, MantineRadius, MantineSize, PolymorphicFactory, StylesApiProps } from '../../core';
import { LoaderProps } from '../Loader';
import { ActionIconGroup } from './ActionIconGroup/ActionIconGroup';
import { ActionIconGroupSection } from './ActionIconGroupSection/ActionIconGroupSection';
export type ActionIconVariant = 'filled' | 'light' | 'outline' | 'transparent' | 'white' | 'subtle' | 'default' | 'gradient';
export type ActionIconStylesNames = 'root' | 'loader' | 'icon';
export type ActionIconCssVariables = {
    root: '--ai-radius' | '--ai-size' | '--ai-bg' | '--ai-hover' | '--ai-hover-color' | '--ai-color' | '--ai-bd';
};
export interface ActionIconProps extends BoxProps, StylesApiProps<ActionIconFactory> {
    'data-disabled'?: boolean;
    __staticSelector?: string;
    /** Determines whether `Loader` component should be displayed instead of the `children`, `false` by default */
    loading?: boolean;
    /** Props added to the `Loader` component (only visible when `loading` prop is set) */
    loaderProps?: LoaderProps;
    /** Controls width and height of the button. Numbers are converted to rem. `'md'` by default. */
    size?: MantineSize | `input-${MantineSize}` | (string & {}) | number;
    /** Key of `theme.colors` or any valid CSS color. Default value is `theme.primaryColor`.  */
    color?: MantineColor;
    /** Key of `theme.radius` or any valid CSS value to set border-radius. Numbers are converted to rem. `theme.defaultRadius` by default. */
    radius?: MantineRadius;
    /** Gradient data used when `variant="gradient"`, default value is `theme.defaultGradient` */
    gradient?: MantineGradient;
    /** Sets `disabled` and `data-disabled` attributes on the button element */
    disabled?: boolean;
    /** Icon displayed inside the button */
    children?: React.ReactNode;
    /** Determines whether button text color with filled variant should depend on `background-color`. If luminosity of the `color` prop is less than `theme.luminosityThreshold`, then `theme.white` will be used for text color, otherwise `theme.black`. Overrides `theme.autoContrast`. */
    autoContrast?: boolean;
}
export type ActionIconFactory = PolymorphicFactory<{
    props: ActionIconProps;
    defaultComponent: 'button';
    defaultRef: HTMLButtonElement;
    stylesNames: ActionIconStylesNames;
    variant: ActionIconVariant;
    vars: ActionIconCssVariables;
    staticComponents: {
        Group: typeof ActionIconGroup;
        GroupSection: typeof ActionIconGroupSection;
    };
}>;
export declare const ActionIcon: (<C = "button">(props: import("../../core").PolymorphicComponentProps<C, ActionIconProps>) => React.ReactElement) & Omit<import("react").FunctionComponent<(ActionIconProps & {
    component?: any;
} & Omit<Omit<any, "ref">, "component" | keyof ActionIconProps> & {
    ref?: any;
    renderRoot?: (props: any) => any;
}) | (ActionIconProps & {
    component: React.ElementType;
    renderRoot?: (props: Record<string, any>) => any;
})>, never> & import("../../core/factory/factory").ThemeExtend<{
    props: ActionIconProps;
    defaultComponent: "button";
    defaultRef: HTMLButtonElement;
    stylesNames: ActionIconStylesNames;
    variant: ActionIconVariant;
    vars: ActionIconCssVariables;
    staticComponents: {
        Group: typeof ActionIconGroup;
        GroupSection: typeof ActionIconGroupSection;
    };
}> & import("../../core/factory/factory").ComponentClasses<{
    props: ActionIconProps;
    defaultComponent: "button";
    defaultRef: HTMLButtonElement;
    stylesNames: ActionIconStylesNames;
    variant: ActionIconVariant;
    vars: ActionIconCssVariables;
    staticComponents: {
        Group: typeof ActionIconGroup;
        GroupSection: typeof ActionIconGroupSection;
    };
}> & import("../../core/factory/polymorphic-factory").PolymorphicComponentWithProps<{
    props: ActionIconProps;
    defaultComponent: "button";
    defaultRef: HTMLButtonElement;
    stylesNames: ActionIconStylesNames;
    variant: ActionIconVariant;
    vars: ActionIconCssVariables;
    staticComponents: {
        Group: typeof ActionIconGroup;
        GroupSection: typeof ActionIconGroupSection;
    };
}> & {
    Group: typeof ActionIconGroup;
    GroupSection: typeof ActionIconGroupSection;
};
