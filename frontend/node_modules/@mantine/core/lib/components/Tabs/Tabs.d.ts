import { BoxProps, ElementProps, Factory, MantineColor, MantineRadius, StylesApiProps } from '../../core';
import { TabsList, TabsListStylesNames } from './TabsList/TabsList';
import { TabsPanel, TabsPanelStylesNames } from './TabsPanel/TabsPanel';
import { TabsTab, TabsTabStylesNames } from './TabsTab/TabsTab';
export type TabsStylesNames = 'root' | TabsListStylesNames | TabsPanelStylesNames | TabsTabStylesNames;
export type TabsVariant = 'default' | 'outline' | 'pills';
export type TabsCssVariables = {
    root: '--tabs-color' | '--tabs-radius';
};
export interface TabsProps extends BoxProps, StylesApiProps<TabsFactory>, ElementProps<'div', 'defaultValue' | 'value' | 'onChange'> {
    /** Default value for uncontrolled component */
    defaultValue?: string | null;
    /** Value for controlled component */
    value?: string | null;
    /** Called when value changes */
    onChange?: (value: string | null) => void;
    /** Tabs orientation, `'horizontal'` by default */
    orientation?: 'vertical' | 'horizontal';
    /** `Tabs.List` placement relative to `Tabs.Panel`, applicable only when `orientation="vertical"`, `'left'` by default */
    placement?: 'left' | 'right';
    /** Base id, used to generate ids to connect labels with controls, generated randomly by default */
    id?: string;
    /** Determines whether arrow key presses should loop though items (first to last and last to first), `true` by default */
    loop?: boolean;
    /** Determines whether tab should be activated with arrow key press, `true` by default */
    activateTabWithKeyboard?: boolean;
    /** Determines whether tab can be deactivated, `false` by default */
    allowTabDeactivation?: boolean;
    /** Tabs content */
    children?: React.ReactNode;
    /** Changes colors of `Tabs.Tab` components when variant is `pills` or `default`, does nothing for other variants */
    color?: MantineColor;
    /** Key of `theme.radius` or any valid CSS value to set `border-radius`, `theme.defaultRadius` by default */
    radius?: MantineRadius;
    /** Determines whether tabs should have inverted styles, `false` by default */
    inverted?: boolean;
    /** If set to `false`, `Tabs.Panel` content will be unmounted when the associated tab is not active, `true` by default */
    keepMounted?: boolean;
    /** Determines whether active item text color should depend on `background-color` of the indicator. If luminosity of the `color` prop is less than `theme.luminosityThreshold`, then `theme.white` will be used for text color, otherwise `theme.black`. Overrides `theme.autoContrast`. Only applicable when `variant="pills"` */
    autoContrast?: boolean;
}
export type TabsFactory = Factory<{
    props: TabsProps;
    ref: HTMLDivElement;
    variant: TabsVariant;
    stylesNames: TabsStylesNames;
    vars: TabsCssVariables;
    staticComponents: {
        Tab: typeof TabsTab;
        Panel: typeof TabsPanel;
        List: typeof TabsList;
    };
}>;
export declare const Tabs: import("../../core").MantineComponent<{
    props: TabsProps;
    ref: HTMLDivElement;
    variant: TabsVariant;
    stylesNames: TabsStylesNames;
    vars: TabsCssVariables;
    staticComponents: {
        Tab: typeof TabsTab;
        Panel: typeof TabsPanel;
        List: typeof TabsList;
    };
}>;
