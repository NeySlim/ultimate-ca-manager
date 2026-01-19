import { BoxProps, CompoundStylesApiProps, MantineColor, PolymorphicFactory } from '../../../core';
export type MenuItemStylesNames = 'item' | 'itemLabel' | 'itemSection';
export interface MenuItemProps extends BoxProps, CompoundStylesApiProps<MenuItemFactory> {
    'data-disabled'?: boolean;
    /** Item label */
    children?: React.ReactNode;
    /** Key of `theme.colors` or any valid CSS color */
    color?: MantineColor;
    /** Determines whether the menu should be closed when the item is clicked, overrides `closeOnItemClick` prop on the `Menu` component */
    closeMenuOnClick?: boolean;
    /** Section displayed on the left side of the label */
    leftSection?: React.ReactNode;
    /** Section displayed on the right side of the label */
    rightSection?: React.ReactNode;
    /** Disables item */
    disabled?: boolean;
}
export type MenuItemFactory = PolymorphicFactory<{
    props: MenuItemProps;
    defaultRef: HTMLButtonElement;
    defaultComponent: 'button';
    stylesNames: MenuItemStylesNames;
    compound: true;
}>;
export declare const MenuItem: (<C = "button">(props: import("../../../core").PolymorphicComponentProps<C, MenuItemProps>) => React.ReactElement) & Omit<import("react").FunctionComponent<(MenuItemProps & {
    component?: any;
} & Omit<Omit<any, "ref">, "component" | keyof MenuItemProps> & {
    ref?: any;
    renderRoot?: (props: any) => any;
}) | (MenuItemProps & {
    component: React.ElementType;
    renderRoot?: (props: Record<string, any>) => any;
})>, never> & import("../../../core/factory/factory").ThemeExtend<{
    props: MenuItemProps;
    defaultRef: HTMLButtonElement;
    defaultComponent: "button";
    stylesNames: MenuItemStylesNames;
    compound: true;
}> & import("../../../core/factory/factory").ComponentClasses<{
    props: MenuItemProps;
    defaultRef: HTMLButtonElement;
    defaultComponent: "button";
    stylesNames: MenuItemStylesNames;
    compound: true;
}> & import("../../../core/factory/polymorphic-factory").PolymorphicComponentWithProps<{
    props: MenuItemProps;
    defaultRef: HTMLButtonElement;
    defaultComponent: "button";
    stylesNames: MenuItemStylesNames;
    compound: true;
}> & Record<string, never>;
