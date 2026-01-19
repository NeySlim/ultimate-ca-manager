import { BoxProps, ElementProps, Factory, MantineSize, StylesApiProps } from '../../../core';
export type PillGroupStylesNames = 'group';
export type PillGroupCssVariables = {
    group: '--pg-gap';
};
export interface PillGroupProps extends BoxProps, StylesApiProps<PillGroupFactory>, ElementProps<'div'> {
    /** Controls spacing between pills, by default controlled by `size` */
    gap?: MantineSize | (string & {}) | number;
    /** Controls size of the child `Pill` components and gap between them, `'sm'` by default */
    size?: MantineSize | (string & {});
    /** Determines whether child `Pill` components should be disabled */
    disabled?: boolean;
}
export type PillGroupFactory = Factory<{
    props: PillGroupProps;
    ref: HTMLDivElement;
    stylesNames: PillGroupStylesNames;
    vars: PillGroupCssVariables;
    ctx: {
        size: MantineSize | (string & {}) | undefined;
    };
}>;
export declare const PillGroup: import("../../../core").MantineComponent<{
    props: PillGroupProps;
    ref: HTMLDivElement;
    stylesNames: PillGroupStylesNames;
    vars: PillGroupCssVariables;
    ctx: {
        size: MantineSize | (string & {}) | undefined;
    };
}>;
