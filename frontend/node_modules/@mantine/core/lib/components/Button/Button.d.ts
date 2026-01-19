import { BoxProps, MantineColor, MantineGradient, MantineRadius, MantineSize, PolymorphicFactory, StylesApiProps } from '../../core';
import { LoaderProps } from '../Loader';
import { ButtonGroup } from './ButtonGroup/ButtonGroup';
import { ButtonGroupSection } from './ButtonGroupSection/ButtonGroupSection';
export type ButtonStylesNames = 'root' | 'inner' | 'loader' | 'section' | 'label';
export type ButtonVariant = 'filled' | 'light' | 'outline' | 'transparent' | 'white' | 'subtle' | 'default' | 'gradient';
export type ButtonCssVariables = {
    root: '--button-justify' | '--button-height' | '--button-padding-x' | '--button-fz' | '--button-radius' | '--button-bg' | '--button-hover' | '--button-hover-color' | '--button-color' | '--button-bd';
};
export interface ButtonProps extends BoxProps, StylesApiProps<ButtonFactory> {
    'data-disabled'?: boolean;
    /** Controls button `height`, `font-size` and horizontal `padding`, `'sm'` by default */
    size?: MantineSize | `compact-${MantineSize}` | (string & {});
    /** Key of `theme.colors` or any valid CSS color, `theme.primaryColor` by default */
    color?: MantineColor;
    /** Sets `justify-content` of `inner` element, can be used to change distribution of sections and label, `'center'` by default */
    justify?: React.CSSProperties['justifyContent'];
    /** Content displayed on the left side of the button label */
    leftSection?: React.ReactNode;
    /** Content displayed on the right side of the button label */
    rightSection?: React.ReactNode;
    /** Determines whether button should take 100% width of its parent container, `false` by default */
    fullWidth?: boolean;
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, `theme.defaultRadius` by default */
    radius?: MantineRadius;
    /** Gradient configuration used when `variant="gradient"`, default value is `theme.defaultGradient` */
    gradient?: MantineGradient;
    /** Indicates disabled state */
    disabled?: boolean;
    /** Button content */
    children?: React.ReactNode;
    /** Determines whether the `Loader` component should be displayed over the button */
    loading?: boolean;
    /** Props added to the `Loader` component (only visible when `loading` prop is set) */
    loaderProps?: LoaderProps;
    /** Determines whether button text color with filled variant should depend on `background-color`. If luminosity of the `color` prop is less than `theme.luminosityThreshold`, then `theme.white` will be used for text color, otherwise `theme.black`. Overrides `theme.autoContrast`. */
    autoContrast?: boolean;
}
export type ButtonFactory = PolymorphicFactory<{
    props: ButtonProps;
    defaultRef: HTMLButtonElement;
    defaultComponent: 'button';
    stylesNames: ButtonStylesNames;
    vars: ButtonCssVariables;
    variant: ButtonVariant;
    staticComponents: {
        Group: typeof ButtonGroup;
        GroupSection: typeof ButtonGroupSection;
    };
}>;
export declare const Button: (<C = "button">(props: import("../../core").PolymorphicComponentProps<C, ButtonProps>) => React.ReactElement) & Omit<import("react").FunctionComponent<(ButtonProps & {
    component?: any;
} & Omit<Omit<any, "ref">, "component" | keyof ButtonProps> & {
    ref?: any;
    renderRoot?: (props: any) => any;
}) | (ButtonProps & {
    component: React.ElementType;
    renderRoot?: (props: Record<string, any>) => any;
})>, never> & import("../../core/factory/factory").ThemeExtend<{
    props: ButtonProps;
    defaultRef: HTMLButtonElement;
    defaultComponent: "button";
    stylesNames: ButtonStylesNames;
    vars: ButtonCssVariables;
    variant: ButtonVariant;
    staticComponents: {
        Group: typeof ButtonGroup;
        GroupSection: typeof ButtonGroupSection;
    };
}> & import("../../core/factory/factory").ComponentClasses<{
    props: ButtonProps;
    defaultRef: HTMLButtonElement;
    defaultComponent: "button";
    stylesNames: ButtonStylesNames;
    vars: ButtonCssVariables;
    variant: ButtonVariant;
    staticComponents: {
        Group: typeof ButtonGroup;
        GroupSection: typeof ButtonGroupSection;
    };
}> & import("../../core/factory/polymorphic-factory").PolymorphicComponentWithProps<{
    props: ButtonProps;
    defaultRef: HTMLButtonElement;
    defaultComponent: "button";
    stylesNames: ButtonStylesNames;
    vars: ButtonCssVariables;
    variant: ButtonVariant;
    staticComponents: {
        Group: typeof ButtonGroup;
        GroupSection: typeof ButtonGroupSection;
    };
}> & {
    Group: typeof ButtonGroup;
    GroupSection: typeof ButtonGroupSection;
};
