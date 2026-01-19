import { BoxProps, CompoundStylesApiProps, ElementProps, Factory } from '../../../core';
export type TabsListStylesNames = 'list';
export interface TabsListProps extends BoxProps, CompoundStylesApiProps<TabsListFactory>, ElementProps<'div'> {
    /** `Tabs.Tab` components */
    children: React.ReactNode;
    /** Determines whether tabs should take all available space, `false` by default */
    grow?: boolean;
    /** Tabs alignment, `flex-start` by default */
    justify?: React.CSSProperties['justifyContent'];
}
export type TabsListFactory = Factory<{
    props: TabsListProps;
    ref: HTMLDivElement;
    stylesNames: TabsListStylesNames;
    compound: true;
}>;
export declare const TabsList: import("../../../core").MantineComponent<{
    props: TabsListProps;
    ref: HTMLDivElement;
    stylesNames: TabsListStylesNames;
    compound: true;
}>;
