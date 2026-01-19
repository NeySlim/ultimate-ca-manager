import { BoxProps, PolymorphicFactory, StylesApiProps } from '../../core';
import { __BaseInputProps, __InputStylesNames, InputVariant } from '../Input';
export interface InputBaseProps extends BoxProps, __BaseInputProps, StylesApiProps<InputBaseFactory> {
    __staticSelector?: string;
    __stylesApiProps?: Record<string, any>;
    /** Props passed down to the root element (`Input.Wrapper` component) */
    wrapperProps?: Record<string, any>;
    /** Determines whether the input can have multiple lines, for example when `component="textarea"`, `false` by default */
    multiline?: boolean;
    /** Determines whether `aria-` and other accessibility attributes should be added to the input, `true` by default */
    withAria?: boolean;
}
export type InputBaseFactory = PolymorphicFactory<{
    props: InputBaseProps;
    defaultRef: HTMLInputElement;
    defaultComponent: 'input';
    stylesNames: __InputStylesNames;
    variant: InputVariant;
}>;
export declare const InputBase: (<C = "input">(props: import("../../core").PolymorphicComponentProps<C, InputBaseProps>) => React.ReactElement) & Omit<import("react").FunctionComponent<(InputBaseProps & {
    component?: any;
} & Omit<Omit<any, "ref">, "component" | keyof InputBaseProps> & {
    ref?: any;
    renderRoot?: (props: any) => any;
}) | (InputBaseProps & {
    component: React.ElementType;
    renderRoot?: (props: Record<string, any>) => any;
})>, never> & import("../../core/factory/factory").ThemeExtend<{
    props: InputBaseProps;
    defaultRef: HTMLInputElement;
    defaultComponent: "input";
    stylesNames: __InputStylesNames;
    variant: InputVariant;
}> & import("../../core/factory/factory").ComponentClasses<{
    props: InputBaseProps;
    defaultRef: HTMLInputElement;
    defaultComponent: "input";
    stylesNames: __InputStylesNames;
    variant: InputVariant;
}> & import("../../core/factory/polymorphic-factory").PolymorphicComponentWithProps<{
    props: InputBaseProps;
    defaultRef: HTMLInputElement;
    defaultComponent: "input";
    stylesNames: __InputStylesNames;
    variant: InputVariant;
}> & Record<string, never>;
