import { BoxProps, CompoundStylesApiProps, ElementProps, Factory, MantineColor } from '../../../core';
export type ProgressSectionStylesNames = 'section';
export interface ProgressSectionProps extends BoxProps, CompoundStylesApiProps<ProgressSectionFactory>, ElementProps<'div'> {
    /** Value of the section in 0–100 range  */
    value: number;
    /** Determines whether `aria-*` props should be added to the root element, `true` by default */
    withAria?: boolean;
    /** Key of `theme.colors` or any valid CSS value, `theme.primaryColor` by default */
    color?: MantineColor;
    /** Determines whether the section should have stripes, `false` by default */
    striped?: boolean;
    /** Determines whether the sections stripes should be animated, if set, `striped` prop is ignored, `false` by default */
    animated?: boolean;
}
export type ProgressSectionFactory = Factory<{
    props: ProgressSectionProps;
    ref: HTMLDivElement;
    stylesNames: ProgressSectionStylesNames;
    compound: true;
}>;
export declare const ProgressSection: import("../../../core").MantineComponent<{
    props: ProgressSectionProps;
    ref: HTMLDivElement;
    stylesNames: ProgressSectionStylesNames;
    compound: true;
}>;
