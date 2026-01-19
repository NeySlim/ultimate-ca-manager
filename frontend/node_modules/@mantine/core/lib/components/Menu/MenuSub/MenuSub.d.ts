import { ExtendComponent, Factory } from '../../../core';
import { FloatingAxesOffsets, FloatingPosition } from '../../Floating';
import { __PopoverProps } from '../../Popover';
import { TransitionOverride } from '../../Transition';
import { MenuSubTarget } from '../MenuSubTarget/MenuSubTarget';
export type MenuSubFactory = Factory<{
    props: MenuSubProps;
}>;
interface MenuSubProps extends __PopoverProps {
    children: React.ReactNode;
    /** Close delay in ms */
    closeDelay?: number;
    /** Dropdown position relative to the target element, `'right-start'` by default */
    position?: FloatingPosition;
    /** Offset of the dropdown element, `0` by default */
    offset?: number | FloatingAxesOffsets;
    /** Props passed down to the `Transition` component that used to animate dropdown presence, use to configure duration and animation type, `{ duration: 150, transition: 'fade' }` by default */
    transitionProps?: TransitionOverride;
}
export declare function MenuSub(_props: MenuSubProps): import("react/jsx-runtime").JSX.Element;
export declare namespace MenuSub {
    var extend: (input: ExtendComponent<MenuSubFactory>) => import("../../../core/factory/factory").ExtendsRootComponent<{
        props: MenuSubProps;
    }>;
    var displayName: string;
    var Target: typeof MenuSubTarget;
    var Dropdown: import("../../../core").MantineComponent<{
        props: import("../MenuSubDropdown/MenuSubDropdown").MenuSubDropdownProps;
        ref: HTMLDivElement;
        stylesNames: import("../MenuSubDropdown/MenuSubDropdown").MenuSubDropdownStylesNames;
        compound: true;
    }>;
    var Item: (<C = "button">(props: import("../../../core").PolymorphicComponentProps<C, import("../MenuSubItem/MenuSubItem").MenuSubItemProps>) => React.ReactElement) & Omit<import("react").FunctionComponent<(import("../MenuSubItem/MenuSubItem").MenuSubItemProps & {
        component?: any;
    } & Omit<Omit<any, "ref">, "component" | keyof import("../MenuSubItem/MenuSubItem").MenuSubItemProps> & {
        ref?: any;
        renderRoot?: (props: any) => any;
    }) | (import("../MenuSubItem/MenuSubItem").MenuSubItemProps & {
        component: React.ElementType;
        renderRoot?: (props: Record<string, any>) => any;
    })>, never> & import("../../../core/factory/factory").ThemeExtend<{
        props: import("../MenuSubItem/MenuSubItem").MenuSubItemProps;
        defaultRef: HTMLButtonElement;
        defaultComponent: "button";
        stylesNames: import("../MenuSubItem/MenuSubItem").MenuSubItemStylesNames;
        compound: true;
    }> & import("../../../core/factory/factory").ComponentClasses<{
        props: import("../MenuSubItem/MenuSubItem").MenuSubItemProps;
        defaultRef: HTMLButtonElement;
        defaultComponent: "button";
        stylesNames: import("../MenuSubItem/MenuSubItem").MenuSubItemStylesNames;
        compound: true;
    }> & import("../../../core/factory/polymorphic-factory").PolymorphicComponentWithProps<{
        props: import("../MenuSubItem/MenuSubItem").MenuSubItemProps;
        defaultRef: HTMLButtonElement;
        defaultComponent: "button";
        stylesNames: import("../MenuSubItem/MenuSubItem").MenuSubItemStylesNames;
        compound: true;
    }> & Record<string, never>;
}
export {};
