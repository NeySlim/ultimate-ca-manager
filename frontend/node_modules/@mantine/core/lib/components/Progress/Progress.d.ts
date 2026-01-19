import { Factory, MantineColor, StylesApiProps } from '../../core';
import { ProgressLabel } from './ProgressLabel/ProgressLabel';
import { __ProgressRootProps, ProgressRoot, ProgressRootCssVariables, ProgressRootStylesNames } from './ProgressRoot/ProgressRoot';
import { ProgressSection } from './ProgressSection/ProgressSection';
export type ProgressStylesNames = ProgressRootStylesNames;
export interface ProgressProps extends __ProgressRootProps, StylesApiProps<ProgressFactory> {
    /** Value of the progress */
    value: number;
    /** Key of `theme.colors` or any valid CSS value, `theme.primaryColor` by default */
    color?: MantineColor;
    /** Determines whether the section should have stripes, `false` by default */
    striped?: boolean;
    /** Determines whether the sections stripes should be animated, if set, `striped` prop is ignored, `false` by default */
    animated?: boolean;
}
export type ProgressFactory = Factory<{
    props: ProgressProps;
    ref: HTMLDivElement;
    stylesNames: ProgressStylesNames;
    vars: ProgressRootCssVariables;
    staticComponents: {
        Section: typeof ProgressSection;
        Root: typeof ProgressRoot;
        Label: typeof ProgressLabel;
    };
}>;
export declare const Progress: import("../../core").MantineComponent<{
    props: ProgressProps;
    ref: HTMLDivElement;
    stylesNames: ProgressStylesNames;
    vars: ProgressRootCssVariables;
    staticComponents: {
        Section: typeof ProgressSection;
        Root: typeof ProgressRoot;
        Label: typeof ProgressLabel;
    };
}>;
