import { BoxProps, CompoundStylesApiProps, ElementProps, Factory } from '../../../core';
export type AccordionControlStylesNames = 'control' | 'chevron' | 'label' | 'itemTitle' | 'icon';
export interface AccordionControlProps extends BoxProps, CompoundStylesApiProps<AccordionControlFactory>, ElementProps<'button'> {
    /** Disables control button */
    disabled?: boolean;
    /** Custom chevron icon */
    chevron?: React.ReactNode;
    /** Control label */
    children?: React.ReactNode;
    /** Icon displayed next to the label */
    icon?: React.ReactNode;
}
export type AccordionControlFactory = Factory<{
    props: AccordionControlProps;
    ref: HTMLButtonElement;
    stylesNames: AccordionControlStylesNames;
    compound: true;
}>;
export declare const AccordionControl: import("../../../core").MantineComponent<{
    props: AccordionControlProps;
    ref: HTMLButtonElement;
    stylesNames: AccordionControlStylesNames;
    compound: true;
}>;
