import { BoxProps, ElementProps, Factory, MantineSpacing, StylesApiProps } from '../../core';
export type BreadcrumbsStylesNames = 'root' | 'separator' | 'breadcrumb';
export type BreadcrumbsCssVariables = {
    root: '--bc-separator-margin';
};
export interface BreadcrumbsProps extends BoxProps, StylesApiProps<BreadcrumbsFactory>, ElementProps<'div'> {
    /** Separator between children, `'/'` by default */
    separator?: React.ReactNode;
    /** Controls spacing between separator and breadcrumb, `'xs'` by default */
    separatorMargin?: MantineSpacing;
    /** React nodes that should be separated with `separator` */
    children: React.ReactNode;
}
export type BreadcrumbsFactory = Factory<{
    props: BreadcrumbsProps;
    ref: HTMLDivElement;
    stylesNames: BreadcrumbsStylesNames;
    vars: BreadcrumbsCssVariables;
}>;
export declare const Breadcrumbs: import("../../core").MantineComponent<{
    props: BreadcrumbsProps;
    ref: HTMLDivElement;
    stylesNames: BreadcrumbsStylesNames;
    vars: BreadcrumbsCssVariables;
}>;
