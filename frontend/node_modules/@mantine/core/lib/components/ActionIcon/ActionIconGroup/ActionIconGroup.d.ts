import { BoxProps, Factory, StylesApiProps } from '../../../core';
export type ActionIconGroupStylesNames = 'group';
export type ActionIconGroupCssVariables = {
    group: '--ai-border-width';
};
export interface ActionIconGroupProps extends BoxProps, StylesApiProps<ActionIconGroupFactory> {
    /** `ActionIcon` components only */
    children?: React.ReactNode;
    /** Controls group orientation, `'horizontal'` by default */
    orientation?: 'horizontal' | 'vertical';
    /** `border-width` of the child `ActionIcon` components. Default value in `1` */
    borderWidth?: number | string;
}
export type ActionIconGroupFactory = Factory<{
    props: ActionIconGroupProps;
    ref: HTMLDivElement;
    stylesNames: ActionIconGroupStylesNames;
    vars: ActionIconGroupCssVariables;
}>;
export declare const ActionIconGroup: import("../../../core").MantineComponent<{
    props: ActionIconGroupProps;
    ref: HTMLDivElement;
    stylesNames: ActionIconGroupStylesNames;
    vars: ActionIconGroupCssVariables;
}>;
