import { Factory } from '../../../core';
import { TooltipBaseProps, TooltipCssVariables, TooltipStylesNames } from '../Tooltip.types';
export interface TooltipFloatingProps extends TooltipBaseProps {
    /** Offset from mouse in px, `10` by default */
    offset?: number;
    /** Uncontrolled tooltip initial opened state */
    defaultOpened?: boolean;
}
export type TooltipFloatingFactory = Factory<{
    props: TooltipFloatingProps;
    ref: HTMLDivElement;
    stylesNames: TooltipStylesNames;
    vars: TooltipCssVariables;
}>;
export declare const TooltipFloating: import("../../../core").MantineComponent<{
    props: TooltipFloatingProps;
    ref: HTMLDivElement;
    stylesNames: TooltipStylesNames;
    vars: TooltipCssVariables;
}>;
