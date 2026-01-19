import { ExtendComponent, Factory, StylesApiProps } from '../../core';
import { __PopoverProps, PopoverStylesNames } from '../Popover';
export type MenuStylesNames = 'item' | 'itemLabel' | 'itemSection' | 'label' | 'divider' | PopoverStylesNames;
export type MenuFactory = Factory<{
    props: MenuProps;
    ref: HTMLDivElement;
    stylesNames: MenuStylesNames;
}>;
export interface MenuProps extends __PopoverProps, StylesApiProps<MenuFactory> {
    variant?: string;
    /** Menu content */
    children?: React.ReactNode;
    /** Controlled menu opened state */
    opened?: boolean;
    /** Uncontrolled menu initial opened state */
    defaultOpened?: boolean;
    /** Determines whether dropdown should trap focus of keyboard events */
    trapFocus?: boolean;
    /** Called when menu opened state changes */
    onChange?: (opened: boolean) => void;
    /** Called when Menu is opened */
    onOpen?: () => void;
    /** Called when Menu is closed */
    onClose?: () => void;
    /** Determines whether Menu should be closed when item is clicked */
    closeOnItemClick?: boolean;
    /** Determines whether arrow key presses should loop though items (first to last and last to first) */
    loop?: boolean;
    /** Determines whether dropdown should be closed when Escape key is pressed */
    closeOnEscape?: boolean;
    /** Event which should open menu */
    trigger?: 'click' | 'hover' | 'click-hover';
    /** Open delay in ms, applicable only to trigger="hover" variant */
    openDelay?: number;
    /** Close delay in ms, applicable only to trigger="hover" variant */
    closeDelay?: number;
    /** Determines whether dropdown should be closed on outside clicks */
    closeOnClickOutside?: boolean;
    /** Events that trigger outside clicks */
    clickOutsideEvents?: string[];
    /** Id base to create accessibility connections */
    id?: string;
    /** Set the `tabindex` on all menu items. Defaults to -1 */
    menuItemTabIndex?: -1 | 0;
    /** Determines whether focus placeholder element should be added before items, `true` by default */
    withInitialFocusPlaceholder?: boolean;
}
export declare function Menu(_props: MenuProps): import("react/jsx-runtime").JSX.Element;
export declare namespace Menu {
    var extend: (input: ExtendComponent<MenuFactory>) => import("../../core/factory/factory").ExtendsRootComponent<{
        props: MenuProps;
        ref: HTMLDivElement;
        stylesNames: MenuStylesNames;
    }>;
    var withProps: (props: Partial<MenuProps>) => MenuProps;
    var classes: Record<string, string>;
    var displayName: string;
    var Item: (<C = "button">(props: import("../../core").PolymorphicComponentProps<C, import("./MenuItem/MenuItem").MenuItemProps>) => React.ReactElement) & Omit<import("react").FunctionComponent<(import("./MenuItem/MenuItem").MenuItemProps & {
        component?: any;
    } & Omit<Omit<any, "ref">, "component" | keyof import("./MenuItem/MenuItem").MenuItemProps> & {
        ref?: any;
        renderRoot?: (props: any) => any;
    }) | (import("./MenuItem/MenuItem").MenuItemProps & {
        component: React.ElementType;
        renderRoot?: (props: Record<string, any>) => any;
    })>, never> & import("../../core/factory/factory").ThemeExtend<{
        props: import("./MenuItem/MenuItem").MenuItemProps;
        defaultRef: HTMLButtonElement;
        defaultComponent: "button";
        stylesNames: import("./MenuItem/MenuItem").MenuItemStylesNames;
        compound: true;
    }> & import("../../core/factory/factory").ComponentClasses<{
        props: import("./MenuItem/MenuItem").MenuItemProps;
        defaultRef: HTMLButtonElement;
        defaultComponent: "button";
        stylesNames: import("./MenuItem/MenuItem").MenuItemStylesNames;
        compound: true;
    }> & import("../../core/factory/polymorphic-factory").PolymorphicComponentWithProps<{
        props: import("./MenuItem/MenuItem").MenuItemProps;
        defaultRef: HTMLButtonElement;
        defaultComponent: "button";
        stylesNames: import("./MenuItem/MenuItem").MenuItemStylesNames;
        compound: true;
    }> & Record<string, never>;
    var Label: import("../../core").MantineComponent<{
        props: import("./MenuLabel/MenuLabel").MenuLabelProps;
        ref: HTMLDivElement;
        stylesNames: import("./MenuLabel/MenuLabel").MenuLabelStylesNames;
        compound: true;
    }>;
    var Dropdown: import("../../core").MantineComponent<{
        props: import("./MenuDropdown/MenuDropdown").MenuDropdownProps;
        ref: HTMLDivElement;
        stylesNames: import("./MenuDropdown/MenuDropdown").MenuDropdownStylesNames;
        compound: true;
    }>;
    var Target: import("react").ForwardRefExoticComponent<import("./MenuTarget/MenuTarget").MenuTargetProps & import("react").RefAttributes<HTMLElement>>;
    var Divider: import("../../core").MantineComponent<{
        props: import("./MenuDivider/MenuDivider").MenuDividerProps;
        ref: HTMLDivElement;
        stylesNames: import("./MenuDivider/MenuDivider").MenuDividerStylesNames;
        compound: true;
    }>;
}
