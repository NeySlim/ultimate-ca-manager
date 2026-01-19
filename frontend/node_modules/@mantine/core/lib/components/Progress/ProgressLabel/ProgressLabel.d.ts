import { BoxProps, CompoundStylesApiProps, ElementProps, Factory } from '../../../core';
export type ProgressLabelStylesNames = 'label';
export interface ProgressLabelProps extends BoxProps, CompoundStylesApiProps<ProgressLabelFactory>, ElementProps<'div'> {
}
export type ProgressLabelFactory = Factory<{
    props: ProgressLabelProps;
    ref: HTMLDivElement;
    stylesNames: ProgressLabelStylesNames;
    compound: true;
}>;
export declare const ProgressLabel: import("../../../core").MantineComponent<{
    props: ProgressLabelProps;
    ref: HTMLDivElement;
    stylesNames: ProgressLabelStylesNames;
    compound: true;
}>;
