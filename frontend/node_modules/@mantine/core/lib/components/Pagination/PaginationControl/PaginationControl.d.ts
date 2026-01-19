import { BoxProps, CompoundStylesApiProps, ElementProps, Factory } from '../../../core';
export type PaginationControlStylesNames = 'control';
export interface PaginationControlProps extends BoxProps, CompoundStylesApiProps<PaginationControlFactory>, ElementProps<'button'> {
    /** Determines whether control should have active styles */
    active?: boolean;
    /** Determines whether control should have padding, true by default */
    withPadding?: boolean;
}
export type PaginationControlFactory = Factory<{
    props: PaginationControlProps;
    ref: HTMLButtonElement;
    stylesNames: PaginationControlStylesNames;
    compound: true;
}>;
export declare const PaginationControl: import("../../../core").MantineComponent<{
    props: PaginationControlProps;
    ref: HTMLButtonElement;
    stylesNames: PaginationControlStylesNames;
    compound: true;
}>;
